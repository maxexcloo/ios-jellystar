import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("touch", ROOT / "tools/touch-report.py")
touch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(touch)


class TouchReportTests(unittest.TestCase):
    def test_sparse_contacts_coordinates_and_release(self):
        # Synthetic wire report: slot 2 at (479,853), slot 4 released,
        # an unused slot, then slot 1 at (0xabc,0xdef), another unused slot.
        data = bytes.fromhex(
            "00 a2 df 55 07 31 02 00 00 00 00 44 00 00 00 00 0f "
            "bc ef 09 da 21 00 00 00 00 0f ff"
        )
        report = touch.decode_report(data)
        self.assertEqual(report["reported_count"], 2)
        self.assertFalse(report["release_all"])
        self.assertEqual(
            report["contacts"],
            [
                {"slot": 2, "event": 0, "active": True, "x": 479, "y": 853, "major": 7},
                {"slot": 4, "event": 4, "active": False, "x": 0, "y": 0, "major": 0},
                {
                    "slot": 1,
                    "event": 2,
                    "active": True,
                    "x": 2748,
                    "y": 3567,
                    "major": 9,
                },
            ],
        )

    def test_zero_count_releases_all_and_empty_records_are_skipped(self):
        data = bytes.fromhex("00 f0" + " 00 00 00 00 0f" * 5 + " 00")
        report = touch.decode_report(data)
        self.assertTrue(report["release_all"])
        self.assertEqual(report["reported_count"], 0)
        self.assertEqual(report["contacts"], [])

    def test_non_touch_reports_do_not_become_contacts(self):
        for status in (0xFC, 0xFD):
            self.assertEqual(
                touch.decode_report(bytes([status]) + bytes(27)),
                {"kind": "ignored", "status": status},
            )
        self.assertEqual(
            touch.decode_report(bytes.fromhex("fe 24") + bytes(26)),
            {"kind": "gesture", "code": 0x24},
        )

    def test_requires_a_complete_report(self):
        for size in (0, 2, 27, 29, 56):
            with self.assertRaisesRegex(ValueError, "expected 28-byte report"):
                touch.decode_report(bytes(size))


if __name__ == "__main__":
    unittest.main()
