#!/usr/bin/env python3
"""Wrap a saved Android boot_a v4 image with an Android-default diagnostic loader."""

import argparse
import gzip
import os
from pathlib import Path
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PAGE = 4096
ALIGNMENT = 0x200000


def align(value, size=PAGE):
    return (value + size - 1) // size * size


def boot_parts(image):
    if image[:8] != b"ANDROID!" or len(image) < PAGE:
        raise ValueError("expected an Android boot image")
    kernel_size, ramdisk_size, _, header_size = struct.unpack_from("<4I", image, 8)
    version = struct.unpack_from("<I", image, 40)[0]
    if (version, header_size) != (4, 1584):
        raise ValueError("only boot header v4 (1584 bytes) is supported")
    ramdisk_offset = PAGE + align(kernel_size)
    if ramdisk_offset + ramdisk_size > len(image):
        raise ValueError("truncated kernel or ramdisk")
    return image[PAGE:PAGE + kernel_size], image[ramdisk_offset:ramdisk_offset + ramdisk_size]


def android_image(kernel):
    raw = gzip.decompress(kernel) if kernel[:2] == b"\x1f\x8b" else kernel
    if raw[56:60] != b"ARM\x64":
        raise ValueError("expected a gzip or raw AArch64 Linux Image")
    offset, size, flags = struct.unpack_from("<3Q", raw, 8)
    if not flags & 8 or flags & 1 or not size:
        raise ValueError("Android Image must be little-endian and support placement anywhere")
    if offset >= ALIGNMENT or offset % PAGE:
        raise ValueError("unsupported Android Image text_offset")
    return raw, offset, max(size, len(raw))


def pack_boot(original, image):
    _, ramdisk = boot_parts(original)
    kernel = gzip.compress(image, compresslevel=9, mtime=0)
    header = bytearray(original[:PAGE])
    struct.pack_into("<I", header, 8, len(kernel))
    # Modifying the kernel invalidates the old GKI signature and AVB footer.
    struct.pack_into("<I", header, 1580, 0)
    return bytes(header) + kernel.ljust(align(len(kernel)), b"\0") + ramdisk.ljust(align(len(ramdisk)), b"\0")


def tool(name):
    if name in os.environ:
        return os.environ[name]
    executable = {"CC": "clang", "LD": "ld.lld", "NM": "llvm-nm",
                  "OBJCOPY": "llvm-objcopy", "READELF": "llvm-readelf"}[name]
    found = shutil.which(executable)
    if found:
        return found
    # Homebrew's LLVM is keg-only; use its own tools without changing host setup.
    path = Path("/opt/homebrew/opt/llvm/bin") / executable
    if path.is_file():
        return str(path)
    raise FileNotFoundError(f"{executable}: set {name} or add LLVM to PATH")


def run(command):
    return subprocess.check_output(command, cwd=ROOT / "shim", text=True)


def facts():
    result = {}
    for line in (ROOT / "devices/jellystar/soc.args").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def build(original, output, diagnostic=False):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    raw, text_offset, extent = android_image(boot_parts(original)[0])
    android = output / "android.bin"
    android.write_bytes(raw.ljust(align(extent), b"\0"))
    android.chmod(0o600)
    # A relative incbin path also handles spaces in the checkout path.
    (output / "android.S").write_text('.section .android, "ax"\n.globl android_image\nandroid_image:\n.incbin "android.bin"\n')
    board = facts()
    defines = {
        "PANEL_WIDTH": board["panel_width"],
        "PANEL_HEIGHT": board["panel_height"],
        "SOC_TOPRGU": board["soc_toprgu"],
        "PMSG_ADDRESS": board["soc_pmsg"] if diagnostic else "0",
        "PMSG_SIZE": board["soc_pmsg_size"],
    }
    (output / "board.h").write_text("".join(f"#define {key} {value}UL\n" for key, value in defines.items()))
    flags = ["--target=aarch64-none-elf", "-mcpu=cortex-a55", "-O2", "-ffreestanding",
             "-nostdlib", "-fno-pic", "-fno-pie", "-fno-stack-protector", "-mgeneral-regs-only",
             "-mstrict-align", "-Wall", "-Wextra", "-Werror", "-I", str(output)]
    objects = []
    for source in [ROOT / "shim/start.S", ROOT / "shim/shim.c", output / "android.S"]:
        obj = output / (source.stem + ".o")
        subprocess.run([tool("CC"), *flags, "-c", str(source), "-o", str(obj)], cwd=output, check=True)
        objects.append(str(obj))
    # Only the Linux header may contain a load-address-independent absolute size.
    relocations = run([tool("READELF"), "-r", *objects])
    if relocations.count("R_AARCH64_ABS64") != 1:
        raise ValueError("unexpected absolute pointers in position-independent loader")
    elf = output / "shim.elf"
    run([tool("LD"), "-m", "aarch64elf", "-T", "link.ld", "--build-id=none",
         f"--defsym=ANDROID_TEXT_OFFSET={text_offset}", *objects, "-o", str(elf)])
    image_path = output / "Image"
    run([tool("OBJCOPY"), "-O", "binary", str(elf), str(image_path)])
    symbols = {parts[2]: int(parts[0], 16) for line in run([tool("NM"), str(elf)]).splitlines()
               if len(parts := line.split()) == 3 and parts[1].upper() in "ABDRT"}
    image = image_path.read_bytes().ljust(symbols["_end"], b"\0")
    embedded = symbols["android_image"]
    if (embedded - text_offset) % ALIGNMENT or image[embedded:embedded + len(raw)] != raw:
        raise ValueError("embedded Android Image placement or contents differ")
    if struct.unpack_from("<Q", image, 16)[0] != len(image):
        raise ValueError("composite Linux Image size differs from header")
    image_path.write_bytes(image)
    image_path.chmod(0o600)
    packed = pack_boot(original, image)
    if len(packed) > len(original):
        raise ValueError("wrapped image exceeds the saved boot partition size")
    kernel, ramdisk = boot_parts(packed)
    if gzip.decompress(kernel) != image or ramdisk != boot_parts(original)[1]:
        raise ValueError("boot image round-trip changed kernel or ramdisk")
    expected_header = bytearray(original[:PAGE])
    struct.pack_into("<I", expected_header, 8, len(kernel))
    struct.pack_into("<I", expected_header, 1580, 0)
    if packed[:PAGE] != expected_header:
        raise ValueError("unexpected boot header change")
    path = output / "chainboot.img"
    path.write_bytes(packed)
    path.chmod(0o600)
    print(f"{path}: {len(packed)} bytes; Android at +{embedded:#x}; ramdisk preserved")
    print("Mode:", "one-shot pmsg colour diagnostic, then Android" if diagnostic else "Android only")
    print("Offline checks passed; Android fallback and LK loading have NOT been tested on hardware.")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("boot", type=Path, help="saved boot_a partition image")
    parser.add_argument("--out", type=Path, default=ROOT / "out/chainboot")
    parser.add_argument("--diagnostic", action="store_true", help="enable the one-shot pmsg diagnostic")
    args = parser.parse_args()
    build(args.boot.read_bytes(), args.out, args.diagnostic)


if __name__ == "__main__":
    main()
