import ctypes
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DisplayPatternTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        facts = {}
        for line in (ROOT / "shim/soc.args").read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                key, value = line.split("=", 1)
                facts[key.strip()] = value.strip()
        cls.width, cls.height = int(facts["panel_width"]), int(facts["panel_height"])
        cls.temp = tempfile.TemporaryDirectory()
        library = Path(cls.temp.name) / "pattern.so"
        subprocess.run(
            [
                "cc",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-shared",
                "-fPIC",
                "-DDISPLAY_PROBE_HOST_TEST",
                f"-DJELLY_WIDTH={cls.width}",
                f"-DJELLY_HEIGHT={cls.height}",
                str(ROOT / "userspace/display-probe.c"),
                "-o",
                str(library),
            ],
            check=True,
        )
        cls.library = ctypes.CDLL(str(library))
        cls.library.jelly_display_pattern.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_bgra_bars_cover_visible_pixels_and_preserve_padding(self):
        stride = self.width * 4 + 64
        size = stride * self.height
        data = ctypes.create_string_buffer(b"\xa5" * (size + 32))
        self.assertEqual(
            self.library.jelly_display_pattern(ctypes.byref(data, 16), size, stride), 1
        )
        raw = data.raw
        self.assertEqual(raw[:16], b"\xa5" * 16)
        self.assertEqual(raw[size + 16 : size + 32], b"\xa5" * 16)
        for x, color in (
            (0, b"\0\0\xff\xff"),
            (64, b"\0\xff\0\xff"),
            (128, b"\xff\0\0\xff"),
            (192, b"\0\0\0\xff"),
        ):
            self.assertEqual(raw[16 + x * 4 : 20 + x * 4], color)
        self.assertEqual(raw[16 + 64 * stride : 20 + 64 * stride], b"\0\0\0\xff")
        end = 16 + (self.height - 1) * stride + (self.width - 1) * 4
        self.assertEqual(raw[end : end + 4], b"\0\0\0\xff")
        for row in range(self.height):
            padding = 16 + row * stride + self.width * 4
            self.assertEqual(raw[padding : padding + 64], b"\xa5" * 64)

    def test_short_storage_is_rejected_before_any_write(self):
        stride = self.width * 4
        size = stride * self.height
        data = ctypes.create_string_buffer(b"\xa5" * size)
        before = data.raw
        for supplied, pitch in ((size - 1, stride), (size, stride - 1)):
            self.assertEqual(
                self.library.jelly_display_pattern(data, supplied, pitch), 0
            )
            self.assertEqual(data.raw, before)


if __name__ == "__main__":
    unittest.main()
