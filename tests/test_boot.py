import ctypes
import gzip
import importlib.util
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "build_shim", ROOT / "tools/build-shim.py"
)
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)


def device_tree(chosen=0xFFB0C000, reserved=0xFFB0C000, size=0x4F3000):
    names = b"atag,videolfb-fb_base_l\0reg\0"

    def node(name):
        text = name.encode() + b"\0"
        return struct.pack(">I", 1) + text.ljust(boot.align(len(text), 4), b"\0")

    def prop(name, value):
        return struct.pack(
            ">III", 3, len(value), names.index(name.encode())
        ) + value.ljust(boot.align(len(value), 4), b"\0")

    end = struct.pack(">I", 2)
    body = (
        node("")
        + node("chosen")
        + prop("atag,videolfb-fb_base_l", struct.pack(">I", chosen))
        + end
    )
    body += (
        node("reserved-memory")
        + node("mblock-13-framebuffer")
        + prop("reg", struct.pack(">QQ", reserved, size))
    )
    body += end * 3 + struct.pack(">I", 9)
    return (
        struct.pack(
            ">10I",
            0xD00DFEED,
            56 + len(body) + len(names),
            56,
            56 + len(body),
            40,
            17,
            16,
            0,
            len(names),
            len(body),
        )
        + b"\0" * 16
        + body
        + names
    )


def saved_boot():
    image = bytearray(8192)
    struct.pack_into("<3Q", image, 8, 0, 4096, 0xA)
    image[56:60] = b"ARM\x64"
    image[-12:] = b"appended-dtb"
    kernel = gzip.compress(bytes(image), mtime=0)
    header = bytearray(4096)
    header[:8] = b"ANDROID!"
    struct.pack_into("<4I", header, 8, len(kernel), 3, 0x18000172, 1584)
    struct.pack_into("<I", header, 40, 4)
    struct.pack_into("<I", header, 1580, 4096)
    header[44:52] = b"console=\0"[:8]
    return bytes(header) + kernel.ljust(boot.align(len(kernel)), b"\0") + b"ram".ljust(
        4096, b"\0"
    ) + b"s" * 4096 + b"AVBf", bytes(image)


class BootImageTests(unittest.TestCase):
    def test_repack_preserves_android_inputs_and_drops_stale_signatures(self):
        original, image = saved_boot()
        raw, offset, extent = boot.android_image(boot.boot_parts(original)[0])
        self.assertEqual(raw, image)
        self.assertEqual(offset, 0)
        self.assertEqual(extent, len(image))
        result = boot.pack_boot(original, b"composite-image")
        self.assertEqual(boot.pack_boot(original, b"composite-image"), result)
        kernel, ramdisk = boot.boot_parts(result)
        self.assertEqual(gzip.decompress(kernel), b"composite-image")
        self.assertEqual(ramdisk, b"ram")
        header = bytearray(original[:4096])
        struct.pack_into("<I", header, 8, len(kernel))
        struct.pack_into("<I", header, 1580, 0)
        self.assertEqual(result[:4096], bytes(header))
        self.assertEqual(len(result), 4096 + boot.align(len(kernel)) + 4096)

    def test_rejects_incompatible_linux_placement(self):
        _, image = saved_boot()
        image = bytearray(image)
        struct.pack_into("<Q", image, 24, 2)
        with self.assertRaisesRegex(ValueError, "placement anywhere"):
            boot.android_image(bytes(image))

    def test_rejects_truncated_boot(self):
        original, _ = saved_boot()
        with self.assertRaisesRegex(ValueError, "truncated"):
            boot.boot_parts(original[:5000])


class LoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / "shim.so"
        subprocess.run(
            [
                "cc",
                "-DSHIM_HOST_TEST",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-shared",
                "-fPIC",
                str(ROOT / "shim/shim.c"),
                "-o",
                str(lib),
            ],
            check=True,
        )
        cls.lib = ctypes.CDLL(str(lib))
        cls.lib.take_trigger.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        cls.lib.framebuffer_from_fdt.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_trigger_is_consumed_and_unrelated_messages_survive(self):
        content = b"other-message\nJELLYSTAR:DIAGNOSTIC\n"
        ring = ctypes.create_string_buffer(
            struct.pack("<III", 0x43474244, len(content), len(content))
            + content
            + b"\0" * 80
        )
        self.assertEqual(self.lib.take_trigger(ring, len(ring) - 1), 1)
        self.assertTrue(ring.raw[12:].startswith(b"other-message\n"))
        self.assertEqual(self.lib.take_trigger(ring, len(ring) - 1), 0)

    def test_trigger_crossing_physical_ring_boundary(self):
        content = b"prefix\nJELLYSTAR:DIAGNOSTIC\nsuffix"
        start = 13
        physical = content[-start:] + content[:-start]
        ring = ctypes.create_string_buffer(
            struct.pack("<III", 0x43474244, start, len(content)) + physical
        )
        self.assertEqual(self.lib.take_trigger(ring, len(ring) - 1), 1)
        self.assertEqual(self.lib.take_trigger(ring, len(ring) - 1), 0)

    def test_invalid_and_unrecorded_triggers_are_ignored(self):
        for signature, start, size in [
            (0, 0, 0),
            (0x43474244, 21, 20),
            (0x43474244, 0, 500),
            (0x43474244, 0, 0),
        ]:
            ring = ctypes.create_string_buffer(
                struct.pack("<III", signature, start, size)
                + b"JELLYSTAR:DIAGNOSTIC"
                + b"\0" * 60
            )
            before = ring.raw
            self.assertEqual(self.lib.take_trigger(ring, len(ring) - 1), 0)
            self.assertEqual(ring.raw, before)

    def test_only_matching_live_framebuffer_is_accepted(self):
        class Framebuffer(ctypes.Structure):
            _fields_ = [("base", ctypes.c_size_t), ("size", ctypes.c_uint64)]

        fb = Framebuffer()
        dtb = ctypes.create_string_buffer(device_tree())
        self.assertEqual(self.lib.framebuffer_from_fdt(dtb, ctypes.byref(fb)), 1)
        self.assertEqual((fb.base, fb.size), (0xFFB0C000, 0x4F3000))
        for data in [device_tree(chosen=0x7E605000), device_tree(size=0), bytes(40)]:
            self.assertEqual(
                self.lib.framebuffer_from_fdt(
                    ctypes.create_string_buffer(data), ctypes.byref(fb)
                ),
                0,
            )


if __name__ == "__main__":
    unittest.main()
