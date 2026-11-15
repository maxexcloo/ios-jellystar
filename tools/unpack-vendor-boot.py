#!/usr/bin/env python3
"""Split the vendor ramdisk out of a boot image header v3/v4 vendor_boot.

  unpack-vendor-boot.py vendor_boot.img [--out DIR]

Writes DIR/vendor_ramdisk.bin (default DIR = alongside the input);
tools/extract-dt.py owns the DTB.

Why not just reuse mkbootimg: the vendor ramdisk here is LZ4 *legacy* frames,
which mkbootimg's python helpers do not care about but python-lz4 refuses
(lz4.frame expects the modern frame format). So the split is done here and the
decode is left to `lz4 -l -d` in tools/unpack-vendor-ramdisk.sh.
"""

import argparse
import os
import struct
import sys
from pathlib import Path

MAGIC = b"VNDRBOOT"


def split(path, out):
    with open(path, "rb") as f:
        hdr = f.read(4096)
        if hdr[:8] != MAGIC:
            sys.exit(f"not a vendor_boot image (magic {hdr[:8]!r})")
        (version,) = struct.unpack_from("<I", hdr, 8)
        if version < 3:
            sys.exit(
                f"header v{version:d} has no vendor ramdisk table; only v3/v4 handled"
            )
        (page,) = struct.unpack_from("<I", hdr, 12)
        (vrs,) = struct.unpack_from("<I", hdr, 24)
        f.seek(page)
        ramdisk = f.read(vrs)

    os.makedirs(out, exist_ok=True)
    path = Path(out) / "vendor_ramdisk.bin"
    path.write_bytes(ramdisk)
    print(f"wrote {path}: v{version:d} header, {vrs:#x} bytes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    split(a.image, a.out or os.path.dirname(os.path.abspath(a.image)))


if __name__ == "__main__":
    main()
