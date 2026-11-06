#!/usr/bin/env python3
"""What differs between a working MT6789 XNU port and this phone.

  diff-port.py [--ref DIR] [--fw DIR]

Reads the reference tree (a checkout of squeeeeezy/HelioDarwin by default, the
Infinix Note 12 2023 port -- same SoC, same Mali-G57, same UFS/DSI/GIC bases) and
prints every constant the port would have to change for the Jelly Star, grouped
by how much work each one is.

It does not edit the reference: the point is a checklist with the file and line
for each item, so the port starts from "these 12 values and these 3 drivers"
instead of "reimplement 200 patches".

  --ref  path to a HelioDarwin checkout (git clone https://github.com/squeeeezy/HelioDarwin)
  --fw   directory holding jellystar.dtb / dtbo.img (tools/extract-dt.py)
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fdt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (label, reference value, jellystar value, where it lives, kind)
#   kind "same"  -> nothing to do, listed so the win is visible
#   kind "edit"  -> a constant in an existing file
#   kind "new"   -> a driver or table that has no counterpart
ITEMS = [
    (
        "GIC distributor",
        "0x0c000000 +0x40000",
        "0x0c000000 +0x40000",
        "x676c/tools/mkadt.py GICD",
        "same",
    ),
    (
        "GIC redistributors",
        "0x0c040000 +0x200000",
        "0x0c040000 +0x200000",
        "x676c/tools/mkadt.py GICR",
        "same",
    ),
    (
        "generic timer",
        "13 MHz, PPI 11 / INTID 27",
        "13 MHz, PPI 11 / INTID 27",
        "x676c/tools/mkadt.py TIMEBASE, VTIMER_INTID",
        "same",
    ),
    (
        "UFS host",
        "0x11270000 +0x2300 SPI 137",
        "0x11270000 +0x2300 SPI 137",
        "x676c/tools/mkadt.py UFS",
        "same",
    ),
    (
        "UFS resets (infracfg_ao)",
        "0x10001000",
        "0x10001000",
        "x676c/tools/mkadt.py INFRACFG_AO",
        "same",
    ),
    (
        "DSI0",
        "0x14013000 SPI 301",
        "0x14013000 SPI 301",
        "x676c/shim/display.c",
        "same",
    ),
    (
        "DISP_MUTEX0",
        "0x14001000 SPI 285",
        "0x14001000 SPI 285",
        "x676c/shim/display.c",
        "same",
    ),
    (
        "Mali GPU",
        "0x13000000 +0x4000 SPI 396-400",
        "0x13000000 +0x4000 SPI 396-400",
        "xnu/patches/01xx-x676c-sweet-mali*",
        "same",
    ),
    (
        "MFG_TOP_CFG",
        "0x13fbf000",
        "0x13fbf000",
        "x676c/tools/mkadt.py (gpufreq)",
        "same",
    ),
    (
        "TOPCKGEN / INFRACFG_AO / GPIO / SPM",
        "0x10000000 / 0x10001000 / 0x10005000 / 0x10006000",
        "0x10000000 / 0x10001000 / 0x10005000 / 0x10006000",
        "x676c/shim/hw.h, xnu/patches/*-x676c-*",
        "same",
    ),
    (
        "PWRAP (MT6366)",
        "0x10026000",
        "0x10026000",
        "x676c/tools/mkadt.py, xnu patches (split SWINF)",
        "same",
    ),
    (
        "TOPRGU (reset)",
        "0x10007000, restart +0x08 key 0x1971",
        "0x10007000, restart +0x08 key 0x1971",
        "x676c/shim/hw.h TOPRGU_BASE/WDT_RESTART",
        "same",
    ),
    (
        "keypad (volume keys)",
        "0x10010000 SPI 106",
        "0x10010000 SPI 106",
        "xnu/patches/0175-*mtk-keypad*",
        "same",
    ),
    (
        "CPU topology",
        "6x A55 published, 2x A76 excluded",
        "6x A55 @0x000-0x500, 2x A76 @0x600/0x700",
        "x676c/tools/mkadt.py CPU_MPIDRS",
        "same",
    ),
    ("CPU page size", "16 KiB", "16 KiB (MT6789)", "xnu MACHINE_CONFIG SWEET", "same"),
    (
        "kernel-managed RAM",
        "0x140000000 +0xffff0000",
        "TBD from the live FDT",
        "x676c/tools/mkadt.py PHYS_BASE/MEM_SIZE, x676c/shim/loader.c KERNEL_RAM_*",
        "edit",
    ),
    (
        "framebuffer base",
        "0xfeabe000 (1080x2400 cmd panel)",
        "0x7e605000 claimed, vramSize 0x1be0000",
        "x676c/tools/mkadt.py FB, FB_SIZE, FB_W/H/STRIDE",
        "edit",
    ),
    (
        "display canvas",
        "1080x2400",
        "480x854 (scale 2 -> 240x427 pt, or a scaled canvas)",
        "x676c/tools/mkadt.py FB_W/FB_H, display-scale",
        "edit",
    ),
    (
        "ECID / chip-id",
        "0x5836373643000001 / 0x8015",
        "pick new synthetics",
        "x676c/tools/mkadt.py X676C_ECID, chip-id",
        "edit",
    ),
    (
        "ADT compatible strings",
        "infinix,x676c",
        "unihertz,jellystar",
        "x676c/tools/mkadt.py root node, /product",
        "edit",
    ),
    (
        "pstore / ramoops reservation",
        "0x48090000 +0xe0000 console 0x4811f000",
        "TBD: read /proc/device-tree/reserved-memory on the phone",
        "x676c/shim/plog.c, xnu patches 0172/0185",
        "edit",
    ),
    (
        "splash / shim console region",
        "LK leaves 0xfeabe000",
        "TBD: atag,videolfb-fb_base_l",
        "x676c/shim/display.c, splash.c",
        "edit",
    ),
    (
        "boot image layout",
        "boot_a via rooted Android B, LK rejects fastboot boot",
        "boot_b via fastboot, virtual A/B, recovery inside vendor_boot",
        "x676c/tools/boot-xnu.ps1 -> rewrite for Linux/fastboot",
        "edit",
    ),
    (
        "root partition",
        "append iosroot to a 64-entry GPT (gpt-split.py)",
        "same idea, different LBA geometry (super is 9 GiB)",
        "x676c/tools/gpt-split.py",
        "edit",
    ),
    (
        "panel driver",
        "ili7835 1080x2400 cmd-mode",
        "ST7701S vdo (480x854) or TD4330 cmd -- two candidates in the overlay",
        "x676c/shim/display.c + xnu DSI patches",
        "new",
    ),
    (
        "touch controller",
        "FocalTech FT5452J, I2C0 0x38",
        "Chipsea chsc5xxx, I2C0 0x2e, IRQ GPIO 9, reset GPIO 152, 10 touches, 3 cap keys",
        "xnu patches 0175/0192/0194 (FT-only today)",
        "new",
    ),
    (
        "touch keys (cap_touch)",
        "none",
        "3 capacitive keys (back/home/recents) via tpd-key-local",
        "xnu HID button mapping",
        "new",
    ),
    (
        "backlight",
        "MT6366/display PWM",
        "disp_pwm0 0x1100e000 through the ST7701S/TD4330 backlight",
        "xnu backlight patches",
        "new",
    ),
    (
        "power key",
        "MT6366 keys via pwrap",
        "MT6366 keys via pwrap, long-press-mode 1",
        "x676c-patch 0175",
        "same",
    ),
]

HEADER = """\
# What changes: HelioDarwin (X676C) -> Jelly Star

Reference: {ref}

Generated by `tools/diff-port.py` from that checkout plus the Jelly Star device
tree. The "same" rows are the reason this port is short: the SoC-level work --
GICv3, the generic timer, MTK UFS, the DSI/disp controller, PWRAP to the MT6366,
topckgen, TOPRGU reset and the Mali-G57 -- is already written and, judging by the
addresses, applies unchanged. The "edit" rows are constants. The "new" rows are
the real work: one panel driver and one touch driver.

"""

REF_URL = "https://github.com/squeeeezy/HelioDarwin"


def describe_ref(path):
    """Name the reference by URL and commit, not by a local directory."""
    if not (path and os.path.isdir(path)):
        return "no checkout (run with --ref)"
    head = os.path.join(path, ".git", "HEAD")
    sha = None
    try:
        with open(head, encoding="utf-8") as f:
            text = f.read().strip()
        if text.startswith("ref:"):
            ref = text.split(":", 1)[1].strip()
            with open(os.path.join(path, ".git", ref), encoding="utf-8") as f:
                sha = f.read().strip()
        else:
            sha = text
    except OSError:
        pass
    return "%s @ %s" % (REF_URL, sha[:12] if sha else "unknown")


def panel_overlay(fw):
    """Which panels the DTBO offers, with their bindings."""
    path = os.path.join(fw, "dtbo.img")
    if not os.path.exists(path):
        return []
    out = []
    for _label, blob in fdt.blobs(open(path, "rb").read()):
        table = {}
        for node, prop, value in fdt.walk(blob):
            table.setdefault(node, {})[prop] = value
        for node, props in sorted(table.items()):
            if re.match(r"^/fragment@\d+/__overlay__/panel\d+@\d+$", node):
                out.append(
                    {
                        "node": node,
                        "compatible": props.get("compatible", b"")
                        .rstrip(b"\0")
                        .decode(),
                        "reg": props.get("reg", b""),
                    }
                )
    return out


def grep(path, pattern):
    """Line numbers in `path` matching `pattern`, for pointing at real code."""
    if not os.path.exists(path):
        return []
    hits = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for no, line in enumerate(f, 1):
            if re.search(pattern, line):
                hits.append((no, line.rstrip()))
    return hits


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--ref",
        default=os.environ.get("HELIODARWIN", os.path.expanduser("~/src/HelioDarwin")),
    )
    ap.add_argument("--fw", default=os.path.join(ROOT, "fw"))
    ap.add_argument(
        "--out", default=os.path.join(ROOT, "docs/jellystar/diff-vs-x676c.md")
    )
    args = ap.parse_args(argv)

    panels = panel_overlay(args.fw)
    lines = [HEADER.format(ref=describe_ref(args.ref))]

    for kind, title, blurb in (
        ("same", "Unchanged", "Addresses and topology that carry over as-is."),
        (
            "edit",
            "Constants to change",
            "One line each; the file that holds it is named.",
        ),
        ("new", "Drivers to write", "No counterpart in the reference tree."),
    ):
        rows = [i for i in ITEMS if i[4] == kind]
        if not rows:
            continue
        lines += ["## %s" % title, "", blurb, ""]
        lines += [
            "| Item | Reference (X676C) | Jelly Star | Where |",
            "|---|---|---|---|",
        ]
        for label, ref_value, new_value, where, _k in rows:
            lines.append(
                "| %s | `%s` | `%s` | `%s` |" % (label, ref_value, new_value, where)
            )
        lines.append("")

    if panels:
        lines += [
            "## Panels the DTBO offers",
            "",
            "The base DTB's `/chosen/atag,videolfb-lcmname` says "
            "`nt36672e_fhdp_dsi_vdo_60hz_jdi_dphy_drv` -- a 1080x2400 "
            "sibling panel, not a 3-inch 480x854 one. The real panel is "
            "selected by the overlay, and the overlay carries two "
            "candidates. Resolve which one is fitted before writing a "
            "driver (see `docs/jellystar/port-plan.md`).",
            "",
            "| Overlay node | compatible | reg |",
            "|---|---|---|",
        ]
        for panel in panels:
            lines.append(
                "| `%s` | `%s` | `%s` |"
                % (panel["node"], panel["compatible"], panel["reg"].hex() or "(0)")
            )
        lines.append("")

    if args.ref and os.path.isdir(args.ref):
        lines += ["## Pointers into the reference tree", ""]
        for label, rel, pattern in (
            (
                "ADT constants",
                "x676c/tools/mkadt.py",
                r"^(PHYS_BASE|MEM_SIZE|FB|FB_W|FB_H|UFS|GICD|GICR|TIMEBASE|SBOX|SOC_BASE)",
            ),
            ("ADT CPU list", "x676c/tools/mkadt.py", r"^CPU_MPIDRS"),
            ("shim RAM window", "x676c/shim/loader.c", r"KERNEL_RAM_(LO|HI)"),
            ("shim SoC registers", "x676c/shim/hw.h", r"^#define\s+\w+_BASE"),
            ("display engine", "x676c/shim/display.c", r"0x1400|0x1401|DSI"),
            (
                "GPT carve",
                "x676c/tools/gpt-split.py",
                r"^(BS|ALIGN|MIN_USERDATA_GIB|HFSPLUS_TYPE)",
            ),
        ):
            hits = grep(os.path.join(args.ref, rel), pattern)
            lines.append("### %s — `%s`" % (label, rel))
            lines.append("")
            if not hits:
                lines.append("*(not found; the reference layout may have moved)*")
            for no, text in hits[:12]:
                lines.append("    %s:%d: %s" % (rel, no, text.strip()))
            lines.append("")

    text = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    counts = {k: sum(1 for i in ITEMS if i[4] == k) for k in ("same", "edit", "new")}
    print(
        "%s: %d unchanged, %d constants, %d new drivers"
        % (
            os.path.relpath(args.out, ROOT),
            counts["same"],
            counts["edit"],
            counts["new"],
        )
    )
    if not (args.ref and os.path.isdir(args.ref)):
        print(
            "note: set HELIODARWIN or --ref to a HelioDarwin checkout for file:line pointers"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
