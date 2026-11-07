#!/usr/bin/env python3
"""Split a boot image header v4 vendor_boot into its vendor ramdisk and DTB.

  unpack-vendor-boot.py vendor_boot.img [--out DIR] [--print-header]

Writes DIR/vendor_ramdisk.bin and DIR/vendor_boot.dtb (default DIR = alongside
the input).

Why not just reuse mkbootimg: the vendor ramdisk here is LZ4 *legacy* frames,
which mkbootimg's python helpers do not care about but python-lz4 refuses
(lz4.frame expects the modern frame format). So the split is done here and the
decode is left to `lz4 -l -d` in tools/unpack-vendor-ramdisk.sh.
"""

import argparse
import os
import struct
import sys

MAGIC = b"VNDRBOOT"


def split(path, out):
    with open(path, "rb") as f:
        hdr = f.read(4096)
        if hdr[:8] != MAGIC:
            sys.exit("not a vendor_boot image (magic %r)" % hdr[:8])
        (version,) = struct.unpack_from("<I", hdr, 8)
        if version < 3:
            sys.exit(
                "header v%d has no vendor ramdisk table; only v3/v4 handled" % version
            )
        (page,) = struct.unpack_from("<I", hdr, 12)
        (vrs,) = struct.unpack_from("<I", hdr, 24)
        (dtb_size,) = struct.unpack_from("<I", hdr, 2100)
        (dtb_addr,) = struct.unpack_from("<Q", hdr, 2104)
        (table_size,) = struct.unpack_from("<I", hdr, 2112)
        (table_num,) = struct.unpack_from("<I", hdr, 2116)

        info = {
            "header_version": version,
            "page_size": page,
            "vendor_ramdisk_size": vrs,
            "dtb_size": dtb_size,
            "dtb_addr": dtb_addr,
            "vendor_ramdisk_table_size": table_size,
            "vendor_ramdisk_table_entries": table_num,
        }

        f.seek(page)
        ramdisk = f.read(vrs)
        off = page + ((vrs + page - 1) // page) * page
        f.seek(off)
        dtb = f.read(dtb_size)
        f.seek(off + ((dtb_size + page - 1) // page) * page)
        table = f.read(table_size)

    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "vendor_ramdisk.bin"), "wb").write(ramdisk)
    open(os.path.join(out, "vendor_boot.dtb"), "wb").write(dtb)
    open(os.path.join(out, "vendor_ramdisk_table.bin"), "wb").write(table)
    info["ramdisk_lz4_legacy"] = ramdisk[:4] == bytes.fromhex("02214c18")
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--out", default=None)
    ap.add_argument("--print-header", action="store_true")
    a = ap.parse_args()
    out = a.out or os.path.dirname(os.path.abspath(a.image))
    info = split(a.image, out)
    for k, v in info.items():
        print("%-32s %s" % (k, hex(v) if isinstance(v, int) else v))
    print("wrote %s/{vendor_ramdisk.bin,vendor_boot.dtb}" % out)


if __name__ == "__main__":
    main()
