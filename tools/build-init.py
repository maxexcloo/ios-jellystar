"""Build the pinned upstream static PID 1 for XNU's mockfs RAM disk.

This is a single signed executable, not an HFS+ filesystem or an iOS root.
The upstream mockfs root exposes these bytes as /sbin/launchd with rd=md0.
macOS codesign verifies the result without executing it.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "out/sources/HelioDarwin")
    parser.add_argument("--out", type=Path, default=ROOT / "out/xnu/init")
    args = parser.parse_args()
    source = args.source.resolve()
    pin = tomllib.loads((ROOT / "xnu/sources.toml").read_text())["helio"]
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != pin["commit"]:
        parser.error(f"HelioDarwin must be checked out at {pin['commit']}")
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "diff",
            "--exit-code",
            "HEAD",
            "--",
            "tools/mkinit.py",
            "tools/sweet-init.S",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    codesign = shutil.which("codesign")
    if codesign is None:
        parser.error("macOS codesign is required to verify the generated executable")
    args.out.mkdir(parents=True, exist_ok=True)
    obj = args.out / "init.o"
    image = args.out / "init"
    subprocess.run(
        [
            os.environ.get("CC", "clang"),
            "-target",
            "arm64-apple-ios16.0",
            "-ffreestanding",
            "-isysroot",
            "/",
            "-c",
            str(source / "tools/sweet-init.S"),
            "-o",
            str(obj),
        ],
        check=True,
    )
    subprocess.run(
        [sys.executable, "-B", str(source / "tools/mkinit.py"), str(obj), str(image)],
        check=True,
    )
    subprocess.run([codesign, "--verify", "--strict", str(image)], check=True)
    print(f"Verified static ARM64 mockfs init: {image} (not executed)")


if __name__ == "__main__":
    main()
