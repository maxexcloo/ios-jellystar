#!/usr/bin/env python3
"""Decode one saved 28-byte CHSC touch report, without accessing a device.

Derived from the local chsc5xxx_touch.ko, semi_touch_irq_handler_imp:
+0x50 reads 28 bytes, +0xc0 advances five-byte records five times,
+0xcc..+0xd8 skips slot 0xf, and +0x170..+0x200 extracts slot, event,
12-bit coordinates and contact size. The DT's ten-touch limit does not
describe this module's five-record wire format. Byte 27 is not interpreted.
semi_touch_mode_init+0x124..+0x12c sets the report address to 0x2000002c;
semi_touch_read_bytes and i2c_read_bytes send the 32-bit address big-endian
before a repeated-start read. No vendor code or firmware is included here.

Coordinates are raw controller coordinates; no panel scaling or orientation
is inferred. This does not implement I2C, reset, firmware loading, virtual
keys, gesture mapping or an XNU input driver.
"""

import argparse
import json
from pathlib import Path

REPORT_BYTES = 28


def decode_report(data):
    if len(data) != REPORT_BYTES:
        raise ValueError(f"expected {REPORT_BYTES}-byte report, got {len(data)}")

    status = data[0]
    if status in (0xFC, 0xFD):
        return {"kind": "ignored", "status": status}
    if status == 0xFE:
        return {"kind": "gesture", "code": data[1]}

    contacts = []
    # The vendor loops over all records, not the count in byte 1.
    for offset in range(2, 27, 5):
        xlo, ylo, major, xyhi, slot_event = data[offset : offset + 5]
        slot = slot_event & 0xF
        if slot == 0xF:
            continue
        event = slot_event >> 4
        contacts.append(
            {
                "slot": slot,
                "event": event,
                "active": event != 4,
                "x": xlo | ((xyhi & 0xF) << 8),
                "y": ylo | ((xyhi >> 4) << 8),
                "major": major,
            }
        )
    count = data[1] & 0xF
    return {
        "kind": "touch",
        "status": status,
        "reported_count": count,
        "release_all": count == 0,
        "contacts": contacts,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="one saved binary report")
    args = parser.parse_args()
    print(json.dumps(decode_report(args.report.read_bytes()), indent=2))


if __name__ == "__main__":
    main()
