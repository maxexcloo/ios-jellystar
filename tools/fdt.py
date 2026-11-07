#!/usr/bin/env python3
"""Minimal flattened-device-tree reader: enough to walk a MediaTek DTB/DTBO and
print the properties a port needs, without libfdt or dtc.

  fdt.py show FILE [PREFIX...]        every property, one per line, full path
  fdt.py get FILE PATH [PROP]         one node's properties (or one value, hex)
  fdt.py nodes FILE [SUBSTR]          just the node paths

A DTBO is a container of DTBs (dt_table_header), so `show` walks every entry and
labels it. Overlay entries are not merged onto a base tree: this reader prints
what each blob literally contains, which is what you want when deciding which of
two panel candidates the vendor actually fitted.

Values are printed as text when they decode as text, else as hex. Cells are
big-endian: a `reg` of 8 bytes is (address, size) u32 pairs.
"""

import os
import sys
from pathlib import Path

MAGIC = 0xD00DFEED
DTBO_MAGIC = 0xD7B7AB1E
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9


def align4(x):
    return (x + 3) & ~3


def blobs(data):
    """Yield (label, dtb_bytes) for a plain DTB or every entry of a DTBO."""
    magic = int.from_bytes(data[:4], "big")
    if magic == MAGIC:
        yield "dtb", data
        return
    if magic != DTBO_MAGIC:
        raise SystemExit(f"not a DTB or DTBO (magic {magic:#x})")
    # dt_table_header: magic, total_size, header_size, entry_size, entry_count,
    # entries_offset, page_size, version
    hdr = [int.from_bytes(data[i * 4 : i * 4 + 4], "big") for i in range(8)]
    total, header_size, entry_size, count, entries_offset = hdr[1:6]
    for i in range(count):
        off = entries_offset + i * entry_size
        size, dtb_off = (
            int.from_bytes(data[off + 4 * j : off + 4 * j + 4], "big") for j in (0, 1)
        )
        label = f"dtbo[{i:d}]"
        # AOSP mkdtimg writes absolute offsets from the start of the image;
        # some vendors write them relative to the end of the table header.
        # Trust the magic, not the spec.
        fdt_magic = MAGIC.to_bytes(4, "big")
        if data[dtb_off : dtb_off + 4] == fdt_magic:
            body = data[dtb_off : dtb_off + size]
        else:
            body = data[header_size + dtb_off : header_size + dtb_off + size]
        start = body.find(fdt_magic)
        yield label, body[start:] if start > 0 else body
    if total > len(data):
        print(
            f"warning: DTBO claims {total:d} bytes, file has {len(data):d}",
            file=sys.stderr,
        )


def walk(dtb):
    """Yield (path, name, value) for every property. value is bytes."""
    tot, off_struct, off_strings = (
        int.from_bytes(dtb[i : i + 4], "big") for i in (4, 8, 12)
    )
    if int.from_bytes(dtb[:4], "big") != MAGIC:
        raise SystemExit("bad FDT magic inside blob")

    def string(off):
        end = dtb.index(b"\0", off)
        return dtb[off:end].decode("utf-8", "replace")

    pos, path = off_struct, []
    while pos < min(tot, len(dtb)):
        tok = int.from_bytes(dtb[pos : pos + 4], "big")
        pos += 4
        if tok == FDT_BEGIN_NODE:
            end = dtb.index(b"\0", pos)
            name = dtb[pos:end].decode("utf-8", "replace")
            pos = align4(end + 1)
            if name:
                path.append(name)
        elif tok == FDT_END_NODE:
            if path:
                path.pop()
        elif tok == FDT_PROP:
            ln = int.from_bytes(dtb[pos : pos + 4], "big")
            nameoff = int.from_bytes(dtb[pos + 4 : pos + 8], "big")
            pos += 8
            value = dtb[pos : pos + ln]
            pos = align4(pos + ln)
            yield "/" + "/".join(path), string(off_strings + nameoff), value
        elif tok == FDT_END:
            return
        elif tok == FDT_NOP:
            continue
        else:
            raise SystemExit(f"bad FDT token {tok:#x} at {pos - 4:d}")


def fmt(value):
    """Text when it decodes as one, else hex. Strings with NULs stay text."""
    if not value:
        return "(empty)"
    try:
        text = value.rstrip(b"\0").decode("utf-8")
        if text and all(32 <= ord(c) < 127 for c in text):
            return repr(text)
    except UnicodeDecodeError:
        pass
    return value.hex()


def u32s(value, width=4):
    return [
        int.from_bytes(value[i : i + width], "big")
        for i in range(0, len(value) - width + 1, width)
    ]


def cmd_show(argv):
    path_prefixes = argv[1:]
    for filename in argv[:1]:
        data = Path(filename).read_bytes()
        for label, dtb in blobs(data):
            print(f"##### {label}")
            for path, name, value in walk(dtb):
                if path_prefixes and not any(path.startswith(p) for p in path_prefixes):
                    continue
                print(f"{path!s:<60} {name!s:<26} {fmt(value)!s}")


def cmd_get(argv):
    if not argv:
        raise SystemExit(__doc__)
    filename = argv[0]
    want = argv[1].rstrip("/") or "/"
    prop = argv[2] if len(argv) > 2 else None
    data = Path(filename).read_bytes()
    hit = False
    for _label, dtb in blobs(data):
        for path, name, value in walk(dtb):
            if path != want or (prop and name != prop):
                continue
            hit = True
            print(f"{name!s:<26} {fmt(value)!s}" if not prop else fmt(value))
    if not hit:
        return 1
    return 0


def cmd_nodes(argv):
    if not argv:
        raise SystemExit(__doc__)
    needle = argv[1] if len(argv) > 1 else ""
    data = Path(argv[0]).read_bytes()
    for _label, dtb in blobs(data):
        seen = []
        for path, _name, _value in walk(dtb):
            if path not in seen:
                seen.append(path)
        for path in seen:
            if needle in path:
                print(path)


def usage(code):
    print(__doc__.strip(), file=sys.stdout if code == 0 else sys.stderr)
    return code


def main(argv):
    if not argv:
        return usage(1)
    if argv[0] in ("-h", "--help"):
        return usage(0)
    cmd = {"show": cmd_show, "get": cmd_get, "nodes": cmd_nodes}.get(argv[0])
    if not cmd:
        return usage(1)
    try:
        return cmd(argv[1:])
    except BrokenPipeError:
        # `fdt.py show ... | head` is a normal thing to do.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
