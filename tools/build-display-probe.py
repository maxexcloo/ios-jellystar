"""Build or verify the iOS 16 Jelly display diagnostic without executing it."""

import argparse
import importlib.util
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify_image(path):
    path = Path(path)
    data = path.read_bytes()
    magic, cpu, subtype, kind, commands, command_bytes, _, _ = struct.unpack_from(
        "<8I", data
    )
    if (magic, cpu, subtype, kind) != (0xFEEDFACF, 0x100000C, 0, 2):
        raise ValueError("Expected a plain ARM64 Mach-O executable")
    end = 32 + command_bytes
    if end > len(data):
        raise ValueError("Truncated Mach-O commands")
    offset, versions = 32, []
    for _ in range(commands):
        command, size = struct.unpack_from("<2I", data, offset)
        if size < 8 or offset + size > end:
            raise ValueError("Invalid Mach-O command bounds")
        if command == 0x32:
            if size < 24:
                raise ValueError("Truncated platform command")
            versions.append(struct.unpack_from("<2I", data, offset + 8))
        offset += size
    if offset != end or versions != [(2, 0x100000)]:
        raise ValueError("Expected the iOS platform with minimum iOS 16.0")
    subprocess.run(["codesign", "--verify", "--strict", str(path)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "out/xnu/display-probe")
    parser.add_argument(
        "--verify", type=Path, help="only verify an existing executable"
    )
    args = parser.parse_args()
    if args.verify:
        verify_image(args.verify)
        print(
            f"Verified iOS 16 ARM64 signature and platform: {args.verify} (not executed)"
        )
        return
    spec = importlib.util.spec_from_file_location(
        "build_shim", ROOT / "tools/build-shim.py"
    )
    boot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boot)
    facts = boot.facts()
    args.out.mkdir(parents=True, exist_ok=True)
    image = args.out / "jelly-display-probe"
    sdk = subprocess.check_output(
        ["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True
    ).strip()
    compiler = subprocess.check_output(
        ["xcrun", "--sdk", "iphoneos", "--find", "clang"], text=True
    ).strip()
    subprocess.run(
        [
            compiler,
            "-target",
            "arm64-apple-ios16.0",
            "-mcpu=cortex-a55",
            "-isysroot",
            sdk,
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            f"-DJELLY_WIDTH={int(facts['panel_width'], 0)}",
            f"-DJELLY_HEIGHT={int(facts['panel_height'], 0)}",
            str(ROOT / "userspace/display-probe.c"),
            "-framework",
            "CoreFoundation",
            "-framework",
            "IOSurface",
            "-o",
            str(image),
        ],
        check=True,
    )
    subprocess.run(
        ["codesign", "--force", "--sign", "-", "--timestamp=none", str(image)],
        check=True,
    )
    verify_image(image)
    print(f"Built and verified iOS 16 ARM64 display probe: {image} (not executed)")


if __name__ == "__main__":
    main()
