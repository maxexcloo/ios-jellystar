"""Prepare the Jelly Star ADT and mockfs payload using pinned MT6789 tooling."""

import argparse
import importlib.util
import os
import struct
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def build_tree(source, board, display=False, touch=False):
    # Keep upstream's required SWEET matching ABI; publish the actual board.
    sys.path.insert(0, str(source / "x676c/tools"))
    mkadt = module("mtk_mkadt", source / "x676c/tools/mkadt.py")
    adt = sys.modules["adt"]
    values = {
        "PHYS_BASE": "soc_dram_kernel_base",
        "MEM_SIZE": "soc_dram_kernel_size",
        "GICD": "soc_gicd",
        "GICD_SIZE": "soc_gicd_size",
        "GICR": "soc_gicr",
        "GICR_SIZE": "soc_gicr_size",
        "TIMEBASE": "soc_timebase",
        "VTIMER_INTID": "soc_vtimer_intid",
        "FB": "soc_fb",
        "FB_SIZE": "soc_fb_reserved",
        "FB_W": "panel_width",
        "FB_H": "panel_height",
    }
    for key, fact in values.items():
        setattr(mkadt, key, int(board[fact], 0))
    mkadt.FB_STRIDE = mkadt.FB_W * 4
    # Single A55 boot CPU until PSCI bring-up is observed on this board.
    mkadt.CPU_MPIDRS = [int(board["soc_cpu_mpidr"].split(",")[0], 0)]
    root = mkadt.build(seed=os.urandom(64), d22ap=None)
    root.props = [
        (k, f, v.replace(b"infinix,x676c", b"unihertz,jellystar"))
        for k, f, v in root.props
    ]
    root.children = [n for n in root.children if n.name not in ("x676c-ufs", "buttons")]
    chosen = next(n for n in root.children if n.name == "chosen")
    # These are upstream Infinix identity values, irrelevant to a PID 1 smoke test.
    chosen.props = [
        (k, f, v)
        for k, f, v in chosen.props
        if k not in ("unique-chip-id", "boot-manifest-hash")
    ]
    chosen.props = [
        (
            k,
            f,
            b"jellystar-shim\0"
            if k in ("firmware-version", "system-firmware-version")
            else v,
        )
        for k, f, v in chosen.props
    ]
    for n in root.children:
        if n.name == "arm-io":
            n.children = [c for c in n.children if c.name == "gic"]
            if display:
                n.children.append(
                    mkadt.node(
                        "disp0",
                        [
                            (
                                "compatible",
                                b"unihertz,jellystar-framebuffer\0sweet,display\0",
                            ),
                            ("device_type", b"display-subsystem\0"),
                            ("canvas-width", struct.pack("<I", mkadt.FB_W)),
                            ("canvas-height", struct.pack("<I", mkadt.FB_H)),
                        ],
                    )
                )
    if touch:
        root.children.append(
            mkadt.node(
                "jellystar-touch",
                [
                    ("compatible", b"unihertz,chsc5xxx\0"),
                ],
            )
        )
    return adt.serialize(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path)
    parser.add_argument("--init", type=Path, default=ROOT / "out/xnu/init/init")
    parser.add_argument("--source", type=Path, default=ROOT / "out/sources/HelioDarwin")
    parser.add_argument("--out", type=Path, default=ROOT / "out/xnu")
    parser.add_argument(
        "--display",
        action="store_true",
        help="opt in to Jelly CPU framebuffer presentation",
    )
    parser.add_argument(
        "--touch",
        action="store_true",
        help="opt in to the CHSC/I2C experiment; MMIO and DMA when booted",
    )
    args = parser.parse_args()
    source = args.source.resolve()
    pin = tomllib.loads((ROOT / "xnu/sources.toml").read_text())["helio"]
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != pin["commit"]:
        parser.error("HelioDarwin checkout differs from xnu/sources.toml")
    subprocess.run(
        ["git", "-C", str(source), "diff", "--exit-code", "HEAD", "--", "x676c/tools"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    boot = module("jelly_boot", ROOT / "tools/build-shim.py")
    args.out.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.out.chmod(0o700)
    tree = build_tree(source, boot.facts(), args.display, args.touch)
    adt_path = args.out / "jellystar.adt"
    adt_path.write_bytes(tree)
    packer = module("mtk_payload", source / "x676c/tools/mkpayload.py")
    cmdline = "debug=0xc serial=3 cpus=1 keepsyms=1 -noprogress rd=md0 sweetmon=0 sweetreboot=0 sweethw=0 sweettouch=0 sweetkeys=0"
    blob, info = packer.build(str(args.kernel), str(adt_path), cmdline, str(args.init))
    # Do not accept arm64e/PAC kernels on the A55.
    if info["cputype"] != "0x100000c" or info["cpusub"] != 0:
        parser.error("a plain arm64 kernel is required")
    payload = args.out / "payload.bin"
    payload.write_bytes(blob)
    payload.chmod(0o600)
    # The segment table and physical memory must agree with the Jelly loader.
    if struct.unpack_from("<2Q", blob, 0x38) != (
        int(boot.facts()["soc_dram_kernel_base"], 0),
        int(boot.facts()["soc_dram_kernel_size"], 0),
    ):
        raise ValueError("payload memory differs from board facts")
    print(f"{payload}: {len(blob)} bytes; Jelly ADT + static init; NOT executed")
    print(f"Opt-in services: display={args.display}, touch={args.touch}")


if __name__ == "__main__":
    main()
