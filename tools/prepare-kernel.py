#!/usr/bin/env python3
"""Prepare pinned XNU sources and the Jelly Star patch stack; optionally build."""

import argparse
import difflib
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def board_header(conf=None):
    if conf is None:
        conf = {}
        for line in (ROOT / "shim/soc.args").read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                key, value = line.split("=", 1)
                conf[key.strip()] = value.strip()
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
        ["git", "-C", str(path), "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        check=False,
    )
    if head.returncode:
        subprocess.run(
            [
                "git",
                "-C",
                str(path),
                "fetch",
                "-q",
                "--depth",
                "1",
                spec["url"],
                spec["commit"],
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "checkout", "-q", "FETCH_HEAD"], check=True
        )
    if git(path, "rev-parse", "HEAD") != spec["commit"]:
        raise ValueError(f"source pin mismatch: {path}")
    return path


def prepare(output, sources):
    import tomllib

    pins = tomllib.loads((ROOT / "xnu/sources.toml").read_text())
    helio = source(sources / "HelioDarwin", pins["helio"])
    builder = source(output / "dxb", pins["dxb"])
    source(builder / "xnu", pins["xnu"])
    patches = builder / "patches"
    upstream_files = git(helio, "ls-files", "xnu/patches").splitlines()
    local_files = git(
        ROOT, "ls-files", "--cached", "--others", "--exclude-standard", "xnu/patches"
    ).splitlines()
    for root, files in ((helio, upstream_files), (ROOT, local_files)):
        for name in files:
            path = root / name
            if path.suffix in (".patch", ".sh"):
                shutil.copy2(path, patches / path.name)
    header = board_header().splitlines()
    (patches / "0211-jellystar-board.patch").write_text(
        "--- /dev/null\n+++ b/pexpert/pexpert/arm64/jellystar.h\n"
        f"@@ -0,0 +1,{len(header)} @@\n" + "".join(f"+{line}\n" for line in header)
    )
    # Stage our original source, while the third-party port remains a pinned dependency.
    device_patch = []
    device_files = git(
        ROOT, "ls-files", "--cached", "--others", "--exclude-standard", "xnu/jellystar"
    ).splitlines()
    for name in device_files:
        path = ROOT / name
        target = "b/bsd/dev/jellystar/" + path.name
        device_patch.extend(
            difflib.unified_diff(
                [],
                path.read_text().splitlines(True),
                fromfile="/dev/null",
                tofile=target,
            )
        )
    (patches / "0212-jellystar-sources.patch").write_text("".join(device_patch))
    build = git(builder, "show", "HEAD:build.sh")
    build = build.replace(
        'ARCHS="x86_64 arm64e" VALID_ARCHS="x86_64 arm64e"',
        'ARCHS="arm64" VALID_ARCHS="arm64" '
        'OTHER_CFLAGS="-mkernel -nostdinc -Wno-packed -mcpu=cortex-a53"',
    )
    # DXB's generic patches may be inapplicable; the numbered port patches must apply.
    old = 'warning "Skipping patch ${PATCH} (already upstream, previously applied, or malformed): ${APPLY_CHECK}"'
    build = build.replace(
        old,
        'case "${PATCH##*/}" in\n'
        '                    [0-9]*.patch) error "Port patch failed: ${PATCH}: ${APPLY_CHECK}"; exit 1 ;;\n'
        f"                    *) {old} ;;\n"
        "                esac",
    )
    (builder / "build.sh").write_text(build + "\n")
    print(f"Prepared {builder}; no kernel has been compiled yet")
    return builder, helio


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
        subprocess.run(["bash", "build.sh"], cwd=builder, env=env, check=True)
        kernel = builder / "fakeroot/System/Library/Kernels/kernel.development.sweet"
        subprocess.run(
            ["python3", str(helio / "x676c/tools/verify-startup.py"), str(kernel)],
            env=env,
            check=True,
        )
        print(f"Built and statically checked {kernel}; execution remains untested")


if __name__ == "__main__":
    main()
