import ctypes
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHYS = 0x140000000
MEMORY = 0xFFFF0000
VIRT = 0xFFFFFE0006000000


def payload():
    data = bytearray(0x400)
    struct.pack_into(
        "<8sII7Q",
        data,
        0,
        b"SWEETXNU",
        1,
        2,
        VIRT,
        VIRT + 0x4000,
        0x3F0,
        16,
        VIRT + 0xC000,
        PHYS,
        MEMORY,
    )
    data[0x48:0x4F] = b"rd=md0\0"
    struct.pack_into("<4Q", data, 0x2A8, VIRT + 0x4000, 0x4000, 0x308, 16)
    struct.pack_into("<4Q", data, 0x2C8, VIRT + 0x8000, 0x4000, 0x318, 16)
    return data


class Layout(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ("entry", "adt", "args", "top")]


class XnuLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / "xnu.so"
        subprocess.run(
            [
                "cc",
                "-DSHIM_HOST_TEST",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-shared",
                "-fPIC",
                str(ROOT / "shim/xnu.c"),
                str(ROOT / "shim/shim.c"),
                "-o",
                str(lib),
            ],
            check=True,
        )
        cls.lib = ctypes.CDLL(str(lib))
        cls.lib.xnu_layout.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_uint64,
            ctypes.c_uint64,
            ctypes.c_void_p,
        ]
        cls.lib.take_marker.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_char_p,
            ctypes.c_size_t,
        ]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def plan(self, data):
        layout = Layout()
        buf = ctypes.create_string_buffer(bytes(data))
        valid = self.lib.xnu_layout(buf, len(data), PHYS, MEMORY, ctypes.byref(layout))
        return valid, layout

    def test_segments_adt_and_boot_args_stay_in_kernel_window(self):
        valid, layout = self.plan(payload())
        self.assertEqual(valid, 1)
        self.assertEqual(
            (layout.entry, layout.adt, layout.args, layout.top),
            (PHYS + 0x4000, PHYS + 0xC000, PHYS + 0x10000, PHYS + 0x14000),
        )

    def test_rejects_truncation_wrong_memory_overlap_and_overflow(self):
        for data in (b"", payload()[:0x300]):
            self.assertEqual(self.plan(data)[0], 0)
        for offset, value in (
            (0x38, PHYS + 0x4000),
            (0x28, 0xFFFFFFFFFFFFFFFF),
            (0x20, 0x2A8),
            (0x18, VIRT),
            (0x30, VIRT + MEMORY),
            (0x2C8, VIRT + 0x4000),
            (0x2B8, 0x3F0),
            (0x2C0, 0x4001),
        ):
            data = payload()
            struct.pack_into("<Q", data, offset, value)
            self.assertEqual(self.plan(data)[0], 0, hex(offset))

    def test_xnu_marker_consumes_only_xnu_request(self):
        content = b"JELLYSTAR:DIAGNOSTIC\nJELLYSTAR:XNU\n"
        data = ctypes.create_string_buffer(
            struct.pack("<III", 0x43474244, len(content), len(content))
            + content
            + bytes(80)
        )
        self.assertEqual(
            self.lib.take_marker(data, len(data) - 1, b"JELLYSTAR:XNU", 13), 1
        )
        self.assertIn(b"JELLYSTAR:DIAGNOSTIC", data.raw)
        self.assertEqual(
            self.lib.take_marker(data, len(data) - 1, b"JELLYSTAR:XNU", 13), 0
        )


if __name__ == "__main__":
    unittest.main()
