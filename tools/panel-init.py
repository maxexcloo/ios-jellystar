#!/usr/bin/env python3
"""Decode the ST7701S panel driver out of the vendor .ko.

  panel-init.py PANEL.ko [--symbol SYM] [--raw]

Prints, from the vendor module itself:

  1. the DCS init sequence as (command, payload) pairs, in the order the driver
     sends them. The vendor compiler emits each sequence element as a small
     local object named after its index (`ST7701S_Z30043_init.d.NN`) in
     .rodata, which is what makes this readable instead of guesswork.
  2. the display timing table, including the pixel clock, so the DRM/DSI timing
     for XNU can be written from measurements rather than a datasheet.

Why this matters: native display bring-up needs the vendor DSI init
sequence for ST7701S". This tool is that step's input. The GIP phases in the
sequence are panel-specific -- they are NOT the values in an ST7701S datasheet
example, and a datasheet sequence is a plausible-looking wrong answer.

The module is in vendor_boot's vendor ramdisk, not /vendor/lib/modules:
  tools/unpack-vendor-ramdisk.sh     (writes recon/vendorboot/ramdisk/lib/modules)
"""

import argparse
import struct
import sys
from pathlib import Path

# ELF64 little-endian aarch64
SHT_SYMTAB = 2
SHT_NOBITS = 8
STT_OBJECT = 1

# The DCS commands an ST7701S init sequence legitimately uses. Used only to
# sanity-check the decode, never to fill anything in.
DCS = {
    0x01: "soft reset",
    0x10: "sleep in",
    0x11: "sleep out",
    0x28: "display off",
    0x29: "display on",
    0x2C: "write_memory_start",
    0x35: "tear on",
    0x36: "address mode",
    0x3A: "pixel format",
    0x51: "brightness",
    0x53: "write CTRL display",
    0xB0: "porch ctrl",
    0xB1: "porch ctrl",
    0xB2: "cmd2 bk3",
    0xB3: "cmd2 bk3",
    0xB7: "GIP ctrl",
    0xB8: "GIP ctrl",
    0xBA: "GIP ctrl",
    0xBB: "GIP ctrl",
    0xBC: "GIP ctrl",
    0xC0: "power ctrl",
    0xC1: "power ctrl",
    0xC2: "power ctrl",
    0xC3: "power ctrl",
    0xC6: "VCOM",
    0xCC: "panel ctrl",
    0xD0: "power ctrl",
    0xE0: "gamma",
    0xE1: "gamma",
    0xE2: "gamma",
    0xE3: "gamma",
    0xE4: "gamma",
    0xE5: "gamma",
    0xE6: "gamma",
    0xE7: "gamma",
    0xE8: "gamma",
    0xE9: "gamma",
    0xEB: "gamma",
    0xEC: "gamma",
    0xED: "gamma",
    0xEE: "gamma",
    0xEF: "gamma",
    0xF0: "page select",
    0xF1: "page select",
    0xF6: "interface ctrl",
    0xFD: "cmd2 enable",
    0xFE: "cmd2 select",
}


def sections(data):
    (shoff,) = struct.unpack_from("<Q", data, 0x28)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 0x3A)
    out = []
    for i in range(shnum):
        sh = shoff + i * shentsize
        name, stype = struct.unpack_from("<II", data, sh)
        flags, addr, off, size = struct.unpack_from("<QQQQ", data, sh + 8)
        link, info, align, entsize = struct.unpack_from("<IIQQ", data, sh + 40)
        out.append(
            {
                "name_off": name,
                "type": stype,
                "flags": flags,
                "addr": addr,
                "off": off,
                "size": size,
                "link": link,
                "info": info,
                "align": align,
                "entsize": entsize,
            }
        )
    strtab_off = out[shstrndx]["off"]
    for s in out:
        end = data.index(b"\0", strtab_off + s["name_off"])
        s["name"] = data[strtab_off + s["name_off"] : end].decode()
    return out


def objects(data, secs, want_prefix):
    """Local OBJECT symbols whose name starts with want_prefix."""
    syms = [s for s in secs if s["type"] == SHT_SYMTAB]
    if not syms:
        return []
    symtab = syms[0]
    strtab = secs[symtab["link"]]
    found = []
    n = symtab["size"] // symtab["entsize"]
    for i in range(n):
        st_name, st_info, _st_other, st_shndx, st_value, st_size = struct.unpack_from(
            "<IBBHQQ", data, symtab["off"] + i * symtab["entsize"]
        )
        if st_info & 0xF != STT_OBJECT or st_shndx == 0 or st_shndx >= len(secs):
            continue
        end = data.index(b"\0", strtab["off"] + st_name)
        name = data[strtab["off"] + st_name : end].decode()
        if name.startswith(want_prefix):
            sec = secs[st_shndx]
            found.append({"name": name, "sec": sec, "value": st_value, "size": st_size})
    return found


def decode_sequence(data, secs, prefix):
    """Turn the vendor's per-element objects into (cmd, payload) pairs."""
    seq = []
    for o in objects(data, secs, prefix):
        sec = o["sec"]
        if sec["type"] == SHT_NOBITS or not o["size"]:
            continue
        rec = data[sec["off"] + o["value"] : sec["off"] + o["value"] + o["size"]]
        if not rec:
            continue
        cmd, payload = rec[0], rec[1:]
        seq.append((o["name"], cmd, payload))
    return seq


def find_timing(data, secs, width, height):
    """Locate the timing table by its active-area values.

    The struct is not packed -- `u16 vactive; pad; u16 hactive; pad; u32
    clock_khz` -- so the two active values are 4 bytes apart, not 2. Require a
    plausible pixel clock too: a bare 480/854 pair can occur by chance.
    """
    hits = []
    want = struct.pack("<H", height) + b"\0\0" + struct.pack("<H", width)
    for s in secs:
        if s["type"] == SHT_NOBITS or s["size"] < 40 or not (s["flags"] & 0x2):
            continue
        blob = data[s["off"] : s["off"] + s["size"]]
        i = blob.find(want)
        while i != -1:
            (clock,) = struct.unpack_from("<I", blob, i + 8)
            if 1000 <= clock <= 200000:
                hits.append((s, i, clock))
            i = blob.find(want, i + 1)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ko")
    ap.add_argument(
        "--symbol",
        default=None,
        help="init-sequence symbol prefix (default: guess from panel name)",
    )
    ap.add_argument("--raw", action="store_true", help="also print raw payload bytes")
    a = ap.parse_args()

    data = Path(a.ko).read_bytes()
    secs = sections(data)

    prefix = a.symbol
    if not prefix:
        for s in secs:
            if s["name"] == ".rodata":
                blob = data[s["off"] : s["off"] + s["size"]]
                if b"zhunyi,st7701,vdo" in blob:
                    prefix = "ST7701S_Z30043_init.d"
        prefix = prefix or "ST7701S_Z30043_init.d"

    seq = decode_sequence(data, secs, prefix)
    print(f"== init sequence ({len(seq):d} objects, symbol prefix {prefix!r})")
    if not seq:
        print("  none found. Wrong module or a stripped build?")
        return 1
    for name, cmd, payload in seq:
        desc = DCS.get(cmd, "")
        if payload:
            body = " ".join(f"{b:02x}" for b in payload)
            print(f"  {name!s:<28} {cmd:02x}  {desc!s:<22}  {body!s}")
        else:
            print(f"  {name!s:<28} {cmd:02x}  {desc!s}")

    print()
    print("== timing table")
    hits = find_timing(data, secs, 480, 854)
    if not hits:
        print("  no 480x854 u16 table found")
        return 0
    for sec, off, clock in hits:
        base = sec["off"] + off
        v = struct.unpack_from("<" + "H" * 18, data, base)
        print("  {!s}+{:d}: {!s}".format(sec["name"], off, " ".join(str(x) for x in v)))
        # Field order, established by checking that clock/(htotal*vtotal) equals the
        # refresh rate the phone reports. Labelled a derivation, not a datasheet.
        hactive, vactive = v[2], v[0]
        hs, he, ht = v[7], v[8], v[9]
        # vactive is repeated at v[11] before the vertical group, which is why the
        # vertical fields start at 12 rather than 10.
        vs, ve, vt = v[12], v[13], v[14]
        print(f"    hactive={hactive:d} vactive={vactive:d} clock={clock:d} kHz")
        print(
            f"    h: bp={hs - hactive:d} sync={he - hs:d} fp={ht - he:d} total={ht:d}"
        )
        print(
            f"    v: bp={vs - vactive:d} sync={ve - vs:d} fp={vt - ve:d} total={vt:d}"
        )
        hz = clock * 1000.0 / (ht * vt)
        print(f"    refresh = {clock:d} kHz / ({ht:d} * {vt:d}) = {hz:.2f} Hz")
        if abs(hz - 60.0) > 0.05:
            print("    NOTE: not 60 Hz -- check the field order before using this")
    return 0


if __name__ == "__main__":
    sys.exit(main())
