"""Check actual pinned ADT generation when upstream sources are available."""

import importlib.util
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "out/sources/HelioDarwin"
spec = importlib.util.spec_from_file_location(
    "payload_builder", ROOT / "tools/build-payload.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
boot = builder.module("jelly_boot_for_test", ROOT / "tools/build-shim.py")


@unittest.skipUnless(
    (SOURCE / "x676c/tools/mkadt.py").is_file(),
    "pinned source needed: tools/prepare-kernel.py",
)
class PayloadTreeTests(unittest.TestCase):
    def tree(self, **features):
        data = builder.build_tree(SOURCE, boot.facts(), **features)
        root, end = sys.modules["adt"].parse(data)
        self.assertEqual(end, len(data))
        return root

    @staticmethod
    def child(node, name):
        return next(c for c in node.children if c.name == name)

    def test_default_smoke_has_no_hardware_services(self):
        root = self.tree()
        armio = self.child(root, "arm-io")
        self.assertEqual([n.name for n in armio.children], ["gic"])
        self.assertNotIn("jellystar-touch", [n.name for n in root.children])
        self.assertNotIn("x676c-ufs", [n.name for n in root.children])
        fb = self.child(root, "sweet-fbcon")
        self.assertEqual(struct.unpack("<2Q", fb.prop("reg")), (0xFFB0C000, 0x4F3000))
        self.assertEqual(
            tuple(
                int.from_bytes(fb.prop(k), "little")
                for k in ("width", "height", "stride")
            ),
            (480, 854, 1920),
        )

    def test_services_require_independent_explicit_options(self):
        for display, touch in ((True, False), (False, True), (True, True)):
            root = self.tree(display=display, touch=touch)
            armio = self.child(root, "arm-io")
            self.assertEqual("disp0" in [n.name for n in armio.children], display)
            self.assertEqual(
                "jellystar-touch" in [n.name for n in root.children], touch
            )
            if display:
                node = self.child(armio, "disp0")
                self.assertEqual(
                    node.prop("compatible"),
                    b"unihertz,jellystar-framebuffer\0sweet,display\0",
                )
                self.assertEqual(
                    int.from_bytes(node.prop("canvas-width"), "little"), 480
                )
                self.assertEqual(
                    int.from_bytes(node.prop("canvas-height"), "little"), 854
                )
            if touch:
                self.assertEqual(
                    self.child(root, "jellystar-touch").prop("compatible"),
                    b"unihertz,chsc5xxx\0",
                )
