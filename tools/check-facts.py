#!/usr/bin/env python3
"""Check shim/soc.args against the phone's own device tree.

  check-facts.py [--fw DIR] [--conf FILE]

Every checkable value in soc.args names the DT node it came from. This re-reads
fw/jellystar.dtb and fw/dtbo.img and reports each as ok / MISMATCH / MISSING, so
a plan that silently drifts from the partition it targets fails loudly here
instead of at the phone. Facts that do not live in the DT (panel geometry, which
comes from the Android side) are listed as SKIP with the reason, never silently
treated as verified.

Get the inputs first:  tools/extract-dt.py vendor_boot.img dtbo.img --out fw
"""

import argparse
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fdt

boot = importlib.import_module("build-shim")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMEBUFFER = "/reserved-memory/mblock-13-framebuffer"

# key -> (tree, node, property, kind, index)
#   kind "reg64": 64-bit (address, size) pairs; index picks a pair.
#   kind "u32":   32-bit cells; index picks a cell.
#   kind "spis":  interrupts <type num flags> groups; collects every num with
#                 type 0 (SPI), which is what a driver wants.
RULES = {
    "soc_gicd": ("dtb", "/interrupt-controller", "reg", "reg64", 0),
    "soc_gicd_size": ("dtb", "/interrupt-controller", "reg", "reg64", 1),
    "soc_gicr": ("dtb", "/interrupt-controller", "reg", "reg64", 2),
    "soc_gicr_size": ("dtb", "/interrupt-controller", "reg", "reg64", 3),
    "soc_timebase": ("dtb", "/timer", "clock-frequency", "u32", 0),
    # The virtual timer follows the two EL1 physical timers.
    "soc_vtimer_intid": ("dtb", "/timer", "interrupts", "intid", 2),
    "soc_ufs": ("dtb", "/soc/ufshci@11270000", "reg", "reg64", 0),
    "soc_ufs_size": ("dtb", "/soc/ufshci@11270000", "reg", "reg64", 1),
    "soc_ufs_spi": ("dtb", "/soc/ufshci@11270000", "interrupts", "u32", 1),
    "soc_infracfg_ao": ("dtb", "/syscon@10001000", "reg", "reg64", 0),
    "soc_topckgen": ("dtb", "/syscon@10000000", "reg", "reg64", 0),
    "soc_apmixedsys": ("dtb", "/syscon@1000C000", "reg", "reg64", 0),
    "soc_scpsys": ("dtb", "/power-controller@10006000", "reg", "reg64", 0),
    "soc_gpio": ("dtb", "/soc/gpio@10005000", "reg", "reg64", 0),
    "soc_pwrap": ("dtb", "/soc/pwrap@10026000", "reg", "reg64", 0),
    "soc_toprgu": ("dtb", "/soc/watchdog@10007000", "reg", "reg64", 0),
    "soc_keypad": ("dtb", "/soc/kp@10010000", "reg", "reg64", 0),
    "soc_disp_pwm": ("dtb", "/soc/disp_pwm0@1100e000", "reg", "reg64", 0),
    "soc_mfg_top_config": ("dtb", "/soc/gpufreq", "reg", "reg64", 0),
    "soc_dsi0": ("dtb", "/soc/dsi@14013000", "reg", "reg64", 0),
    "soc_dsi0_spi": ("dtb", "/soc/dsi@14013000", "interrupts", "u32", 1),
    "soc_disp_mutex0": ("dtb", "/soc/disp_mutex@14001000", "reg", "reg64", 0),
    "soc_fb": ("live", FRAMEBUFFER, "reg", "reg64", 0),
    "soc_fb_reserved": ("live", FRAMEBUFFER, "reg", "reg64", 1),
    "soc_fb_vramsize": ("live", "/chosen", "atag,videolfb-vramSize", "u32", 0),
    "soc_pstore": ("live", "/reserved-memory/mblock-10-pstore", "reg", "reg64", 0),
    "soc_pstore_size": ("live", "/reserved-memory/mblock-10-pstore", "reg", "reg64", 1),
    "soc_aee_kinfo": (
        "live",
        "/reserved-memory/mblock-9-aee_debug_kinfo",
        "reg",
        "reg64",
        0,
    ),
    "soc_minirdump": (
        "live",
        "/reserved-memory/mblock-11-minirdump",
        "reg",
        "reg64",
        0,
    ),
    "soc_dram_rank0_end": (
        "live",
        "/reserved-memory/mblock-1-dramc-rk0",
        "reg",
        "reg64",
        0,
    ),
    "soc_dram_rank1_end": (
        "live",
        "/reserved-memory/mblock-2-dramc-rk1",
        "reg",
        "reg64",
        0,
    ),
    "soc_gpu": ("dtb", "/soc/mali@13000000", "reg", "reg64", 0),
    "soc_gpu_size": ("dtb", "/soc/mali@13000000", "reg", "reg64", 1),
    "soc_gpu_spis": ("dtb", "/soc/mali@13000000", "interrupts", "spis", None),
    "soc_usb": ("dtb", "/soc/usb0@11200000", "reg", "reg64", 0),
    "soc_usb_phy": ("dtb", "/soc/usb0@11200000", "reg", "reg64", 2),
    "soc_touch_i2c_size": ("dtb", "/soc/i2c@11e00000", "reg", "reg64", 1),
    "soc_touch_dma": ("dtb", "/soc/i2c@11e00000", "reg", "reg64", 2),
    "soc_touch_dma_size": ("dtb", "/soc/i2c@11e00000", "reg", "reg64", 3),
    "soc_touch_clock": ("dtb", "/syscon@11E02000", "reg", "reg64", 0),
    "soc_touch_iocfg_lm": ("dtb", "/soc/pinctrl", "reg", "reg64", 8),
    "soc_touch_i2c": ("dtb", "/soc/i2c@11e00000", "reg", "reg64", 0),
    "soc_touch_addr": (
        "dtbo",
        "/fragment@34/__overlay__/cap_touch@38",
        "reg",
        "u32",
        0,
    ),
    "soc_touch_hz": ("dtbo", "/fragment@34/__overlay__", "clock-frequency", "u32", 0),
    "soc_touch_irq_gpio": (
        "dtbo",
        "/fragment@34/__overlay__/cap_touch@38",
        "chipsemi,int-gpio",
        "u32",
        1,
    ),
    "soc_touch_rst_gpio": (
        "dtbo",
        "/fragment@34/__overlay__/cap_touch@38",
        "chipsemi,rst-gpio",
        "u32",
        1,
    ),
    "soc_touch_irq_type": (
        "dtbo",
        "/fragment@34/__overlay__/cap_touch@38",
        "interrupts",
        "u32",
        1,
    ),
    "soc_touch_xres": (
        "dtbo",
        "/fragment@34/__overlay__/cap_touch@38",
        "tpd-resolution",
        "u32",
        0,
    ),
    "soc_touch_yres": (
        "dtbo",
        "/fragment@34/__overlay__/cap_touch@38",
        "tpd-resolution",
        "u32",
        1,
    ),
    "soc_touch_max": (
        "dtbo",
        "/fragment@34/__overlay__/cap_touch@38",
        "tpd-max-touch-num",
        "u32",
        0,
    ),
}

# Facts asserted by the plan that are simply not in the device tree. Printed
# with the reason so nobody mistakes them for verified.
NOT_IN_DT = {
    "panel_width": "verified on the phone: DRM mode 480x854",
    "panel_height": "verified on the phone: DRM mode 480x854",
    "panel_density": "verified on the phone: wm density 220",
    "panel_driver": "verified on the phone: lsmod panel_ST7701S_Z30043",
    "panel_mode": "verified on the phone: lsmod vdo panel",
    # Panel timing and init sequence are decoded from the vendor panel module,
    # not the DT: tools/panel-init.py re-derives each of these.
    "panel_htotal": "decoded from panel-ST7701S_Z30043.ko (tools/panel-init.py)",
    "panel_vtotal": "decoded from panel-ST7701S_Z30043.ko (tools/panel-init.py)",
    "panel_hbp": "decoded from panel-ST7701S_Z30043.ko (tools/panel-init.py)",
    "panel_hfp": "decoded from panel-ST7701S_Z30043.ko (tools/panel-init.py)",
    "panel_hsync": "decoded from panel-ST7701S_Z30043.ko (tools/panel-init.py)",
    "panel_vbp": "decoded from panel-ST7701S_Z30043.ko (tools/panel-init.py)",
    "panel_vfp": "decoded from panel-ST7701S_Z30043.ko (tools/panel-init.py)",
    "panel_vsync": "decoded from panel-ST7701S_Z30043.ko (tools/panel-init.py)",
    "panel_clock_khz": "decoded: 28000 kHz / (522*894) = 60.00 Hz, matches DRM",
    "panel_init_objects": "decoded from panel-ST7701S_Z30043.ko (tools/panel-init.py)",
    "panel_init_sym": "decoded from panel-ST7701S_Z30043.ko (tools/panel-init.py)",
    "soc_fb_lcmname": "the packaged DTB's value is WRONG for this phone (see panel_driver)",
    "soc_lk_lcmname": "LK boot log only (expdb): LK says ST7701S_Z30043_drv, /chosen disagrees",
    "soc_touch_scl_gpio": "pinctrl-mt6789: GPIO130 function1 is SCL0; not a DT property",
    "soc_touch_sda_gpio": "pinctrl-mt6789: GPIO131 function1 is SDA0; not a DT property",
    "soc_touch_driver": "verified on the phone: lsmod chsc5xxx_touch",
    "soc_touch_input": "verified on the phone: /proc/bus/input/devices event2",
    "soc_touch_fw_embedded": "decoded from chsc5xxx_touch.ko: .rodata upd_data, 85848 B, magic CHSC",
    "soc_touch_fw_bytes": "decoded from chsc5xxx_touch.ko (magic CHSC)",
    "soc_touch_proto": "decoded from chsc5xxx_touch.ko: BE32 report address + repeated-start read",
    "soc_touch_report_parse": "decoded from chsc5xxx_touch.ko: semi_touch_irq_handler_imp",
    "soc_mmsys_config": "not present in this DTB",
    "soc_ovl0": "not present in this DTB",
    # Storage geometry comes from /proc/partitions and blockdev, not the DT.
    "soc_lun": "/proc/partitions: the UFS LUN is sdc",
    "soc_block": "/sys/block/sdc/queue/logical_block_size = 4096",
    "soc_lun_bytes": "/sys/block/sdc/size x 4096",
    "part_userdata_bytes": "blockdev --getsize64: 228.0 GiB",
    "part_userdata_kib": "/proc/partitions column 3 is KiB, not sectors",
    "part_super_bytes": "blockdev --getsize64: 9.0 GiB",
    "part_super_kib": "/proc/partitions column 3 is KiB, not sectors",
    "part_expdb_bytes": "blockdev --getsize64: 128 MiB (LK log ring)",
}


def load(fw):
    paths = {
        "dtb": os.path.join(fw, "jellystar.dtb"),
        "dtbo": os.path.join(fw, "dtbo.img"),
    }
    # The live DT captured by tools/recon.sh is optional. Without it the live
    # rows report SKIP.
    live = os.path.join(ROOT, "recon", "live.dtb")
    if os.path.exists(live):
        paths["live"] = live
    trees = {}
    for name, path in paths.items():
        if not os.path.exists(path):
            sys.exit(
                f"check-facts: missing {path} (run tools/extract-dt.py ... --out fw)"
            )
        trees[name] = []
        for _label, blob in fdt.blobs(Path(path).read_bytes()):
            table = {}
            for node, prop, value in fdt.walk(blob):
                table.setdefault(node, {})[prop] = value
            trees[name].append(table)
    return trees


def prop_of(trees, src, node, prop):
    for tree in trees[src]:
        if node in tree and prop in tree[node]:
            return tree[node][prop]
    return None


def want_list(text):
    return [int(token, 0) for token in text.replace(",", " ").split()]


def got_for(value, kind, index):
    cells = fdt.u32s(value)
    if kind == "reg64":
        pairs = [(cells[i] << 32) | cells[i + 1] for i in range(0, len(cells) - 1, 2)]
        return pairs if index is None else [pairs[index]]
    if kind == "spis":
        return [cells[i + 1] for i in range(0, len(cells) - 3, 4) if cells[i] == 0]
    if kind == "intid":
        # A PPI (type 1) becomes INTID 16 + num.
        start = 4 * index
        if start + 4 > len(cells):
            raise IndexError(index)
        return [16 + cells[start + 1]] if cells[start] == 1 else []
    return cells if index is None else [cells[index]]


def derived_value(trees, key):
    if "live" not in trees:
        return None
    if key.startswith(("soc_pmsg", "soc_console")):
        value = prop_of(trees, "live", "/chosen", "bootargs")
        if value is None:
            return None
        args = dict(
            token.split("=", 1)
            for token in value.rstrip(b"\0").decode().split()
            if token.startswith("ramoops.") and "=" in token
        )
        size = int(args["ramoops.pmsg_size"], 0)
        if key.startswith("soc_console"):
            console = int(args["ramoops.console_size"], 0)
            if key == "soc_console_size":
                return console
            # Linux 5.10 ramoops defaults: ftrace_size=4096. record_size
            # affects dump record division, not the dump/console boundary.
            ftrace = int(args.get("ramoops.ftrace_size", "4096"), 0)
            return (
                int(args["ramoops.mem_address"], 0)
                + int(args["ramoops.mem_size"], 0)
                - size
                - ftrace
                - console
            )
        if key == "soc_pmsg_size":
            return size
        return (
            int(args["ramoops.mem_address"], 0)
            + int(args["ramoops.mem_size"], 0)
            - size
        )
    rank0 = prop_of(trees, "live", "/reserved-memory/mblock-1-dramc-rk0", "reg")
    rank1 = prop_of(trees, "live", "/reserved-memory/mblock-2-dramc-rk1", "reg")
    if rank0 is None or rank1 is None:
        return None
    base = int.from_bytes(rank0[:8], "big") + 0x1000
    if key == "soc_dram_kernel_base":
        return base
    # Preserve the reference's conservative 64 KiB alignment below the training page.
    return (int.from_bytes(rank1[:8], "big") - base) & ~0xFFFF


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--fw", default=os.path.join(ROOT, "fw"))
    ap.add_argument("--conf", default=os.path.join(ROOT, "shim/soc.args"))
    args = ap.parse_args(argv)

    trees = load(args.fw)
    facts = boot.facts(args.conf)
    bad = skipped = 0

    for key in sorted(facts):
        expected = facts[key]
        if key in (
            "soc_console",
            "soc_console_size",
            "soc_pmsg",
            "soc_pmsg_size",
            "soc_dram_kernel_base",
            "soc_dram_kernel_size",
        ):
            got = derived_value(trees, key)
            if got is None:
                print(f"{key!s:<22} SKIP    requires the saved live DT")
                skipped += 1
            elif got != int(expected, 0):
                print(f"{key!s:<22} MISMATCH derived={got:#x} conf={expected!s}")
                bad += 1
            else:
                print(f"{key!s:<22} ok      {got:#x} (derived from live DT)")
            continue
        if key in NOT_IN_DT:
            print(f"{key!s:<22} SKIP    {NOT_IN_DT[key]!s}")
            skipped += 1
            continue
        if key == "soc_cpu_mpidr":
            continue  # checked below, as a set
        rule = RULES.get(key)
        if rule is None:
            print(f"{key!s:<22} SKIP    no rule in check-facts.py")
            skipped += 1
            continue
        src, node, prop, kind, index = rule
        if src not in trees:
            print(f"{key!s:<22} SKIP    requires the saved live DT")
            skipped += 1
            continue
        value = prop_of(trees, src, node, prop)
        if value is None:
            print(f"{key!s:<22} MISSING {node!s} {prop!s}")
            bad += 1
            continue
        try:
            got = got_for(value, kind, index)
        except IndexError:
            print(
                f"{key!s:<22} MISSING {node!s} {prop!s} too short for index {index!r}"
            )
            bad += 1
            continue
        want = want_list(expected)
        if got != want:
            print(
                "{!s:<22} MISMATCH dt={!s} conf={!s}".format(
                    key, ",".join(hex(x) for x in got), ",".join(hex(x) for x in want)
                )
            )
            bad += 1
        else:
            print("{!s:<22} ok      {!s}".format(key, ",".join(hex(x) for x in got)))

    # CPU topology is a set, not a single cell: the plan must not claim a core
    # the tree does not have, or drop one it does.
    cpus = []
    for tree in trees["dtb"]:
        for path, node in tree.items():
            if path.startswith("/cpus/cpu@") and "reg" in node:
                cpus.append(fdt.u32s(node["reg"])[0])
    want_cpus = want_list(facts["soc_cpu_mpidr"])
    if sorted(cpus) != sorted(want_cpus):
        print(
            "{!s:<22} MISMATCH dt={!s} conf={!s}".format(
                "soc_cpu_mpidr",
                ",".join(hex(x) for x in sorted(cpus)),
                ",".join(hex(x) for x in want_cpus),
            )
        )
        bad += 1
    else:
        print(
            "{!s:<22} ok      {:d} cores ({:d} A55 + {:d} A76)".format(
                "soc_cpu_mpidr",
                len(cpus),
                sum(1 for c in cpus if c < 0x600),
                sum(1 for c in cpus if c >= 0x600),
            )
        )

    print()
    if bad:
        print(f"{bad:d} fact(s) disagree with the device tree, {skipped:d} skipped")
        return 1
    print(f"all checkable facts match the device tree ({skipped:d} skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
