#!/usr/bin/env python3
"""Pull the device tree out of a Jelly Star vendor_boot.img, plus the DTBO.

  extract-dt.py VENDOR_BOOT_IMG [DTBO_IMG] --out DIR

Writes DIR/jellystar.dtb (the DTB embedded in the vendor_boot header) and, when
a dtbo image is given, DIR/dtbo.img. Nothing is decompressed: vendor_boot v4
stores the DTB uncompressed after the vendor ramdisk.

Where the images come from (pick the one matching what is installed):

  * LineageOS release 20261101 (or newer):
      https://github.com/osquera/lineageos_unihertz_jellystar/releases
      -> vendor_boot.img, dtbo.img
  * Unihertz stock Android 16 firmware (V01.00.04 or later), images/
      -> vendor_boot.img, dtbo.img

Both are vendor binaries and are not redistributable; they stay out of git
(fw/ is ignored) and are only read here to source addresses and node names.
"""

import argparse
import os
import struct
import sys
from pathlib import Path

VNDRBOOT = b"VNDRBOOT"
DTBO_MAGIC = 0xD7B7AB1E
FDT_MAGIC = 0xD00DFEED


def page_align(x, page):
    return (x + page - 1) // page * page


def parse_vendor_boot(data):
    """Return (dtb_bytes, header_dict) for a vendor_boot header v3/v4 image."""
    if data[:8] != VNDRBOOT:
        raise SystemExit(f"not a vendor_boot image (magic {data[:8]!r})")
    # vendor_boot_img_hdr_v3/v4: magic, header_version, page_size,
    # kernel_addr, ramdisk_addr, vendor_ramdisk_size, cmdline[2048],
    # tags_addr, name[16], header_size, dtb_size, dtb_addr
    version, page = struct.unpack_from("<II", data, 8)
    if version < 3:
        raise SystemExit(f"vendor_boot header v{version:d} has no DTB")
    ramdisk_size = struct.unpack_from("<I", data, 24)[0]
    _header_size, dtb_size = struct.unpack_from("<II", data, 2096)
    dtb_addr = struct.unpack_from("<Q", data, 2104)[0]
    cmdline = data[28 : 28 + 2048].split(b"\0")[0].decode("utf-8", "replace")

    dtb_off = page_align(page + page_align(ramdisk_size, page), page)
    # The DTB need not start on the page boundary: stock images place it
    # 64-byte aligned somewhere inside that first page, so find the magic.
    window = data[dtb_off : dtb_off + page + dtb_size + page]
    start = window.find(FDT_MAGIC.to_bytes(4, "big"))
    if start < 0:
        raise SystemExit(f"no FDT at {dtb_off:#x} in the vendor ramdisk tail")
    dtb = window[start : start + dtb_size]
    return dtb, {
        "header_version": version,
        "page_size": page,
        "vendor_ramdisk_size": ramdisk_size,
        "dtb_size": dtb_size,
        "dtb_addr": dtb_addr,
        "cmdline": cmdline,
    }


def describe(dtb):
    """The handful of facts that decide whether a port plan still applies."""
    out = {}
    for key, off, width in (
        ("total", 4, 4),
        ("off_struct", 8, 4),
        ("off_strings", 12, 4),
    ):
        out[key] = int.from_bytes(dtb[off : off + width], "big")
    return out


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("vendor_boot")
    ap.add_argument("dtbo", nargs="?")
    ap.add_argument("--out", default="fw")
    args = ap.parse_args(argv)

    dtb, hdr = parse_vendor_boot(Path(args.vendor_boot).read_bytes())
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "jellystar.dtb")
    with open(path, "wb") as f:
        f.write(dtb)
    print(
        "{!s}: {:d} bytes (header v{:d}, page {:d}, ramdisk {:d}, dtb_addr {:#x})".format(
            path,
            len(dtb),
            hdr["header_version"],
            hdr["page_size"],
            hdr["vendor_ramdisk_size"],
            hdr["dtb_addr"],
        )
    )
    print(f"fdt: {describe(dtb)!r}")

    if args.dtbo:
        blob = Path(args.dtbo).read_bytes()
        if int.from_bytes(blob[:4], "big") != DTBO_MAGIC:
            raise SystemExit(
                "{}: not a DTBO (magic {:#x})".format(
                    args.dtbo, int.from_bytes(blob[:4], "big")
                )
            )
        dst = os.path.join(args.out, "dtbo.img")
        with open(dst, "wb") as f:
            f.write(blob)
        count = int.from_bytes(blob[16:20], "big")
        print(f"{dst!s}: {len(blob):d} bytes, {count:d} overlay entries")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
