import ctypes
import importlib.util
import random
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "touch_report", ROOT / "tools/touch-report.py"
)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


class Contact(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_uint16),
        ("y", ctypes.c_uint16),
        ("slot", ctypes.c_uint8),
        ("event", ctypes.c_uint8),
        ("major", ctypes.c_uint8),
        ("active", ctypes.c_uint8),
    ]


class Report(ctypes.Structure):
    _fields_ = [
        ("kind", ctypes.c_uint8),
        ("status", ctypes.c_uint8),
        ("reported_count", ctypes.c_uint8),
        ("contact_count", ctypes.c_uint8),
        ("gesture", ctypes.c_uint8),
        ("contacts", Contact * 5),
    ]


class State(ctypes.Structure):
    _fields_ = [("slots", Contact * 15)]


class Startup(ctypes.Structure):
    _fields_ = [
        ("signature", ctypes.c_uint32),
        ("vendor_product", ctypes.c_uint32),
        ("firmware_version", ctypes.c_uint16),
        ("raw_offset", ctypes.c_uint16),
        ("diff_offset", ctypes.c_uint16),
        ("status", ctypes.c_uint8),
    ]


def wire_report(count, contacts=()):
    data = bytearray(b"\0" + bytes([count]) + b"\0\0\0\0\x0f" * 5 + b"\0")
    for index, (slot, event, x, y, major) in enumerate(contacts):
        data[2 + 5 * index : 7 + 5 * index] = bytes(
            [x & 255, y & 255, major, (x >> 8) | ((y >> 8) << 4), slot | event << 4]
        )
    return bytes(data)


class ChscProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        library = Path(cls.temp.name) / "chsc.so"
        subprocess.run(
            [
                "cc",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-shared",
                "-fPIC",
                str(ROOT / "xnu/jellystar/chsc.c"),
                "-o",
                str(library),
            ],
            check=True,
        )
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.chsc_address.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        cls.lib.chsc_decode_report.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(Report),
        ]
        cls.lib.chsc_decode_startup.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(Startup),
        ]
        cls.lib.chsc_state_init.argtypes = [ctypes.POINTER(State)]
        cls.lib.chsc_apply_report.argtypes = [
            ctypes.POINTER(Report),
            ctypes.POINTER(State),
        ]
        cls.lib.chsc_active_mask.argtypes = [ctypes.POINTER(State)]
        cls.lib.chsc_active_mask.restype = ctypes.c_uint16

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def decode(self, data):
        report = Report()
        self.assertEqual(self.lib.chsc_decode_report(data, len(data), report), 1)
        return report

    def test_native_decoder_agrees_with_wire_reference(self):
        samples = [
            wire_report(
                2, [(2, 0, 479, 853, 7), (4, 4, 0, 0, 0), (14, 2, 4095, 4095, 255)]
            ),
            wire_report(0),
            bytes.fromhex("fc 01") + bytes(26),
            bytes.fromhex("fd 00") + bytes(26),
            bytes.fromhex("fe 24") + bytes(26),
        ]
        # Independent Python decoder covers the same protocol; varied wire
        # fields catch nibble order, slot skipping and signedness differences.
        generator = random.Random(6789)
        samples += [generator.randbytes(28) for _ in range(64)]
        for data in samples:
            expected = reference.decode_report(data)
            actual = self.decode(data)
            self.assertEqual(actual.status, data[0])
            self.assertEqual(
                actual.kind, {"touch": 1, "ignored": 2, "gesture": 3}[expected["kind"]]
            )
            if actual.kind == 3:
                self.assertEqual(actual.gesture, expected["code"])
            elif actual.kind == 1:
                self.assertEqual(actual.reported_count, expected["reported_count"])
                contacts = [
                    {
                        "x": contact.x,
                        "y": contact.y,
                        "slot": contact.slot,
                        "event": contact.event,
                        "major": contact.major,
                        "active": bool(contact.active),
                    }
                    for contact in actual.contacts[: actual.contact_count]
                ]
                self.assertEqual(contacts, expected["contacts"])

    def test_protocol_b_state_retains_omissions_and_last_release_position(self):
        state = State()
        self.lib.chsc_state_init(state)
        self.assertEqual(self.lib.chsc_active_mask(state), 0)
        report = self.decode(wire_report(1, [(14, 0, 479, 853, 7)]))
        self.assertEqual(self.lib.chsc_apply_report(report, state), 1)
        self.assertEqual(self.lib.chsc_active_mask(state), 1 << 14)
        self.lib.chsc_apply_report(
            self.decode(wire_report(2, [(2, 2, 10, 20, 3)])), state
        )
        self.assertEqual(self.lib.chsc_active_mask(state), (1 << 14) | (1 << 2))
        self.lib.chsc_apply_report(
            self.decode(wire_report(1, [(14, 4, 0, 0, 0)])), state
        )
        self.assertEqual(self.lib.chsc_active_mask(state), 1 << 2)
        self.assertEqual((state.slots[14].x, state.slots[14].y), (479, 853))
        before = bytes(state)
        for data in (
            bytes.fromhex("fd 00") + bytes(26),
            bytes.fromhex("fe 24") + bytes(26),
        ):
            self.assertEqual(self.lib.chsc_apply_report(self.decode(data), state), 0)
            self.assertEqual(bytes(state), before)
        # A zero count releases everything even if records contain stale data.
        self.lib.chsc_apply_report(
            self.decode(wire_report(0, [(3, 0, 1, 2, 3)])), state
        )
        self.assertEqual(self.lib.chsc_active_mask(state), 0)
        self.assertEqual((state.slots[2].x, state.slots[2].y), (10, 20))

    def test_startup_header_and_address_byte_orders(self):
        for signature, status in ((0x43534843, 1), (0x4F525245, 2), (0, 0)):
            data = struct.pack(
                "<HHIIHH", 0x1234, 0xFFFF, signature, 0xABCDEF01, 0x102, 0x304
            )
            header = Startup()
            self.assertEqual(self.lib.chsc_decode_startup(data, len(data), header), 1)
            self.assertEqual(header.status, status)
            self.assertEqual(header.signature, signature)
            self.assertEqual(header.vendor_product, 0xABCDEF01)
            self.assertEqual(
                (header.firmware_version, header.raw_offset, header.diff_offset),
                (0x1234, 0x102, 0x304),
            )
        for address, expected in (
            (0x2000002C, b"\x20\0\0\x2c"),
            (0x12345678, b"\x12\x34\x56\x78"),
        ):
            command = ctypes.create_string_buffer(4)
            self.lib.chsc_address(address, command)
            self.assertEqual(command.raw, expected)

    def test_incomplete_wire_reads_do_not_publish_partial_results(self):
        for structure, function, sizes in (
            (Report, self.lib.chsc_decode_report, (0, 2, 27, 29)),
            (Startup, self.lib.chsc_decode_startup, (0, 4, 15, 17)),
        ):
            for size in sizes:
                result = structure()
                ctypes.memset(ctypes.byref(result), 0xA5, ctypes.sizeof(result))
                before = bytes(result)
                self.assertEqual(function(bytes(size), size, result), 0)
                self.assertEqual(bytes(result), before)


if __name__ == "__main__":
    unittest.main()
