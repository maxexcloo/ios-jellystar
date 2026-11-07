import ctypes
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READ16 = ctypes.CFUNCTYPE(ctypes.c_uint16, ctypes.c_void_p, ctypes.c_uint)
WRITE16 = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint16)
READ32 = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint)
WRITE32 = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint32)
DELAY = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint)
SYNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t)


class Operations(ctypes.Structure):
    _fields_ = [
        ("read16", READ16),
        ("write16", WRITE16),
        ("dma_read32", READ32),
        ("dma_write32", WRITE32),
        ("delay_us", DELAY),
        ("sync", SYNC),
    ]


class Bus(ctypes.Structure):
    _fields_ = [
        ("io", ctypes.POINTER(Operations)),
        ("context", ctypes.c_void_p),
        ("tx", ctypes.POINTER(ctypes.c_uint8)),
        ("rx", ctypes.POINTER(ctypes.c_uint8)),
        ("tx_phys", ctypes.c_uint64),
        ("rx_phys", ctypes.c_uint64),
        ("rx_capacity", ctypes.c_size_t),
        ("poll_limit", ctypes.c_uint),
        ("faulted", ctypes.c_int),
        ("dma_quiet", ctypes.c_int),
        ("status", ctypes.c_uint16),
    ]


class Controller:
    """A noncoherent DMA endpoint: CPU sees RX only after sync and DMA idle."""

    def __init__(self, mode="success"):
        self.mode = mode
        self.events = []
        self.controller = {0x10: 0x28}
        self.dma = {}
        self.started = False
        self.valid_transfer = False
        self.tx_device = b""
        self.rx_prepared = False
        self.report = bytes(range(28))
        self.tx = (ctypes.c_uint8 * 64)()
        self.rx = (ctypes.c_uint8 * 128)(*[0xA5] * 128)
        self.ops = Operations(
            READ16(self.read16),
            WRITE16(self.write16),
            READ32(self.read32),
            WRITE32(self.write32),
            DELAY(self.delay),
            SYNC(self.sync),
        )
        self.bus = Bus(
            ctypes.pointer(self.ops),
            None,
            self.tx,
            self.rx,
            0x140000000,
            0x140000080,
            128,
            8,
            0,
            1,
            0,
        )

    def read16(self, _, offset):
        self.events.append(("read16", offset))
        if offset == 0x0C and self.started:
            if self.mode in ("timeout", "stuck_timeout"):
                return 0
            if self.mode == "nack_complete":
                return 3
            if self.mode == "nack" or not self.valid_transfer:
                return 2
            if self.mode == "arbitration":
                return 8
            if self.mode != "stuck_done":
                self.dma[8] = 0
                self.controller[0x24] = 0
            return 1
        return self.controller.get(offset, 0)

    def write16(self, _, offset, value):
        self.events.append(("write16", offset, value))
        self.controller[offset] = value
        if offset == 0x24 and value == 1:
            self.started = True
            # Verify the wire transaction and full 36-bit DMA addresses.
            self.valid_transfer = (
                self.tx_device == bytes.fromhex("20 00 00 2c")
                and self.rx_prepared
                and self.controller[0x94] == 0x5C
                and self.controller[0x14] == 4
                and self.controller[0x44] == len(self.report)
                and self.controller[0x18] == 2
                and self.controller[0x10] & 0x33E == 0x33E
                and self.dma[8] == 1
                and self.dma[0x18] == 0x214
                and (self.dma[0x54] << 32 | self.dma[0x1C]) == self.bus.tx_phys
                and (self.dma[0x58] << 32 | self.dma[0x20]) == self.bus.rx_phys
                and self.dma[0x24] == 4
                and self.dma[0x28] == len(self.report)
            )

    def read32(self, _, offset):
        self.events.append(("read32", offset))
        return self.dma.get(offset, 0)

    def write32(self, _, offset, value):
        self.events.append(("write32", offset, value))
        self.dma[offset] = value
        if offset == 0x0C and value == 6 and not self.mode.startswith("stuck_"):
            self.dma[8] = 0

    def delay(self, _, _usec):
        self.events.append(("delay",))

    def sync(self, _, direction, size):
        self.events.append(("sync", direction, size))
        if direction == 0:
            self.tx_device = bytes(self.tx[:size])
        elif direction == 1:
            self.rx_prepared = True
        elif direction == 2 and not self.dma.get(8, 0):
            for index, value in enumerate(self.report):
                self.rx[index] = value


class I2cTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        library = Path(cls.temp.name) / "i2c.so"
        subprocess.run(
            [
                "cc",
                "-shared",
                "-fPIC",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(ROOT / "xnu/jellystar/i2c.c"),
                "-o",
                str(library),
            ],
            check=True,
        )
        cls.library = ctypes.CDLL(str(library))
        cls.library.jelly_i2c_quiesce.argtypes = [ctypes.POINTER(Bus)]
        cls.library.jelly_i2c_read.argtypes = [
            ctypes.POINTER(Bus),
            ctypes.c_uint8,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_size_t,
        ]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def transfer(self, controller, size=28):
        output = (ctypes.c_uint8 * 28)(*[0x55] * 28)
        result = self.library.jelly_i2c_read(
            ctypes.byref(controller.bus), 0x2E, 0x2000002C, output, size
        )
        return result, bytes(output)

    def test_combined_report_uses_high_dma_bits_and_cache_handoff(self):
        controller = Controller()
        result, output = self.transfer(controller)
        self.assertEqual(result, 0)
        self.assertTrue(controller.valid_transfer)
        self.assertEqual(output, controller.report)
        self.assertTrue(controller.bus.dma_quiet)
        self.assertFalse(controller.bus.faulted)
        self.assertEqual(
            [e for e in controller.events if e[0] == "sync"],
            [("sync", 0, 4), ("sync", 1, 28), ("sync", 2, 28)],
        )

    def test_busy_controller_does_not_take_buffers_or_start_transfer(self):
        for controller_busy in (True, False):
            controller = Controller()
            if controller_busy:
                controller.controller[0x24] = 1
            else:
                controller.dma[8] = 1
            result, output = self.transfer(controller)
            self.assertEqual(result, -2)
            self.assertFalse(controller.started)
            self.assertEqual(output, b"\x55" * 28)
            self.assertFalse(
                any(e[0] in ("sync", "write16", "write32") for e in controller.events)
            )

    def test_error_resets_dma_preserves_output_and_requires_setup(self):
        for mode, expected in (
            ("nack", -3),
            ("nack_complete", -3),
            ("arbitration", -6),
            ("timeout", -4),
        ):
            controller = Controller(mode)
            result, output = self.transfer(controller)
            self.assertEqual(result, expected)
            self.assertEqual(output, b"\x55" * 28)
            self.assertTrue(controller.bus.faulted)
            self.assertTrue(controller.bus.dma_quiet)
            self.assertNotIn(("sync", 2, 28), controller.events)
            count = len(controller.events)
            self.assertEqual(self.transfer(controller)[0], -5)
            self.assertEqual(len(controller.events), count)

    def test_stuck_dma_is_never_reused_or_exposed_to_cpu(self):
        for mode in ("stuck_done", "stuck_timeout"):
            controller = Controller(mode)
            result, output = self.transfer(controller)
            self.assertEqual(result, -5)
            self.assertTrue(controller.bus.faulted)
            self.assertFalse(controller.bus.dma_quiet)
            self.assertEqual(output, b"\x55" * 28)
            self.assertNotIn(("sync", 2, 28), controller.events)
            self.assertEqual(self.transfer(controller)[0], -5)

    def test_explicit_quiesce_latches_setup_requirement_and_checks_dma_idle(self):
        for mode, expected, quiet in (("success", 0, True), ("stuck_done", -5, False)):
            controller = Controller(mode)
            controller.dma[8] = 1
            self.assertEqual(
                self.library.jelly_i2c_quiesce(ctypes.byref(controller.bus)), expected
            )
            self.assertTrue(controller.bus.faulted)
            self.assertEqual(bool(controller.bus.dma_quiet), quiet)
            self.assertEqual(self.transfer(controller)[0], -5)
            self.assertNotIn(("sync", 2, 28), controller.events)

    def test_invalid_dma_extents_and_lengths_fail_before_io(self):
        for tx, rx, size in (
            (0x1000000000, 0x140000080, 28),
            (0x140000000, 0xFFFFFFFC0, 128),
            (0x140000000, 0x140000000, 28),
            (0x140000000, 0x140000081, 28),
            (0x140000000, 0x140000080, 0),
            (0x140000000, 0x140000080, 129),
        ):
            controller = Controller()
            controller.bus.tx_phys, controller.bus.rx_phys = tx, rx
            self.assertEqual(self.transfer(controller, size)[0], -1)
            self.assertEqual(controller.events, [])


if __name__ == "__main__":
    unittest.main()
