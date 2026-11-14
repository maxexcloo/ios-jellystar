#!/usr/bin/env python3
"""Fetch pinned XNU sources; optionally patch and build the Jelly Star kernel."""

import argparse
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def board_header():
    spec = importlib.util.spec_from_file_location(
        "build_shim", ROOT / "tools/build-shim.py"
    )
    boot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boot)
    conf = boot.facts()
    values = {
        "FB_SIZE": int(conf["soc_fb_reserved"], 0),
        "TOUCH_I2C": int(conf["soc_touch_i2c"], 0),
        "TOUCH_I2C_SIZE": int(conf["soc_touch_i2c_size"], 0),
        "TOUCH_DMA": int(conf["soc_touch_dma"], 0),
        "TOUCH_DMA_SIZE": int(conf["soc_touch_dma_size"], 0),
        "TOUCH_CLOCK": int(conf["soc_touch_clock"], 0),
        "TOUCH_IOCFG_LM": int(conf["soc_touch_iocfg_lm"], 0),
        "TOUCH_GPIO": int(conf["soc_gpio"], 0),
        "TOUCH_INFRA": int(conf["soc_infracfg_ao"], 0),
        "TOUCH_TOPCKGEN": int(conf["soc_topckgen"], 0),
        "TOUCH_SCL": int(conf["soc_touch_scl_gpio"], 0),
        "TOUCH_SDA": int(conf["soc_touch_sda_gpio"], 0),
        "TOUCH_ADDRESS": int(conf["soc_touch_addr"], 0),
        "TOUCH_XRES": int(conf["soc_touch_xres"], 0),
        "TOUCH_YRES": int(conf["soc_touch_yres"], 0),
        "TOUCH_MAX": int(conf["soc_touch_max"], 0),
        "FB_PA": int(conf["soc_fb"], 0),
        "FB_WIDTH": int(conf["panel_width"], 0),
        "FB_HEIGHT": int(conf["panel_height"], 0),
        "FB_STRIDE": int(conf["panel_width"], 0) * 4,
        "PSTORE_PA": int(conf["soc_console"], 0),
        "PSTORE_SIZE": int(conf["soc_console_size"], 0),
    }
    return (
        "/* Generated from shim/soc.args by tools/prepare-kernel.py. */\n"
        "#pragma once\n"
        + "".join(f"#define JELLY_{key} 0x{value:x}\n" for key, value in values.items())
    )


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def source(path, spec):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    head = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--verify", "-q", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if head != spec["commit"]:
        git(path, "fetch", "-q", "--depth", "1", spec["url"], spec["commit"])
    git(path, "checkout", "-q", "-f", spec["commit"])
    return path


def prepare(output, sources):
    pins = tomllib.loads((ROOT / "xnu/sources.toml").read_text())
    helio = source(sources / "HelioDarwin", pins["helio"])
    builder = source(output / "dxb", pins["dxb"])
    source(builder / "xnu", pins["xnu"])
    script = builder / "build.sh"
    script.write_text(
        script.read_text().replace(
            'ARCHS="x86_64 arm64e" VALID_ARCHS="x86_64 arm64e"',
            'ARCHS="arm64" VALID_ARCHS="arm64" '
            'OTHER_CFLAGS="-mkernel -nostdinc -Wno-packed -mcpu=cortex-a53"',
        )
    )
    print(f"Prepared {builder}; no kernel has been compiled yet")
    return builder, helio


def patch(xnu, helio, env):
    git(xnu, "clean", "-fdxq")
    (xnu / "pexpert/pexpert/arm64/jellystar.h").write_text(board_header())
    shutil.copytree(ROOT / "xnu/jellystar", xnu / "bsd/dev/jellystar")
    # DXB's order: every staging script, then every patch, sorted by name.
    port = sorted(
        [*(helio / "xnu/patches").iterdir(), *(ROOT / "xnu/patches").iterdir()],
        key=lambda path: path.name,
    )
    for path in port:
        if path.suffix == ".sh":
            subprocess.run(["bash", str(path)], cwd=xnu, env=env, check=True)
    for path in port:
        if path.suffix == ".patch":
            git(xnu, "apply", str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "out/kernel")
    parser.add_argument("--sources", type=Path, default=ROOT / "out/sources")
    parser.add_argument(
        "--build", action="store_true", help="run the macOS/Xcode kernel build"
    )
    args = parser.parse_args()
    builder, helio = prepare(args.out.resolve(), args.sources.resolve())
    if args.build:
        iig = helio / "x676c/tools/iig-8796.py"
        env = os.environ.copy()
        env.update(
            MACOS_VERSION="13.5",
            KERNEL_CONFIG="DEVELOPMENT",
            MACHINE_CONFIG="SWEET",
            IIG=shlex.join([sys.executable, str(iig)]),
            MAKEFLAGS=f"OTHER_CXXFLAGS=-include{helio}/x676c/tools/iig-8796-abi.h",
        )
        patch(builder / "xnu", helio, env)
        subprocess.run(["bash", "build.sh"], cwd=builder, env=env, check=True)
        kernel = builder / "fakeroot/System/Library/Kernels/kernel.development.sweet"
        subprocess.run(
            [sys.executable, str(helio / "x676c/tools/verify-startup.py"), str(kernel)],
            env=env,
            check=True,
        )
        print(f"Built and statically checked {kernel}; execution remains untested")


if __name__ == "__main__":
    main()
