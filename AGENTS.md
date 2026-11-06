# AGENTS.md

Working on `ios-jellystar`. Read `README.md`, then `docs/jellystar/port-plan.md`, then
`docs/jellystar/diff-vs-x676c.md`. The reference port is `squeeeezy/HelioDarwin` (Infinix Note 12 2023,
same MT6789 SoC); `lib-fluff-so/KLiOS716` is the second opinion and the source of the boot discipline.

## Truth rules

- **Nothing is "working" until the phone showed it.** `devices/jellystar/device.conf` is the only status
  list, and its convention is `works|partial|missing`. A device-tree property, a compiled driver or a
  successful CI run is not a working subsystem. This repository currently claims nothing works.
- A fact in `devices/jellystar/soc.args` names the DT node it came from. `tools/check-facts.py` re-reads
  `fw/jellystar.dtb` and `fw/dtbo.img` and must stay green; if it fails, the fact is wrong or the DT is
  not the one on the phone.
- Keep observations and guesses apart, in writing. "The overlay offers two panels" is an observation;
  "the ST7701S is fitted" is a guess until `getprop`/`dmesg` says so.
- Record each milestone (successful or not) at the top of `NOTES.md` with the kernel/image hash, the boot
  slot, and what the panel showed.

## Device safety

- **`boot_b` only.** Android stays on `_a` as the way back. Never flash `boot_a`, never relock the
  bootloader, never use "Format All + Download" in SP Flash Tool (it erases IMEI/calibration).
- `fastboot boot` does not work on MediaTek LK; every test is a slot flash.
- Back up `persist`, `modemst1`, `modemst2`, `fsg`, `fsc`, `nvdata`, `nvcfg` before anything destructive,
  and keep the dumps off git (they carry IMEI).
- Unbrick path: SP Flash Tool v6 + **Android 16** stock firmware, "Firmware Upgrade" or "Download Only".
  The original Android 13 firmware cannot be flashed (anti-rollback).
- Wiping `userdata` is what installing the root image does. Confirm with the user, out loud, immediately
  before it happens.

## Keep out of git

- `fw/` — vendor `vendor_boot`/`dtbo`/`boot` images and the DTBs extracted from them (Unihertz binaries).
- `recon/` — anything read off the phone: live DT (has the serial), `expdb`, `dmesg` dumps, partition
  dumps, MAC addresses, IMEI.
- Apple's files: IPSW parts, the iOS root image, the shared cache, the static trust cache.
- The iOS root image and any `*.img` produced from vendor or Apple material.

## Where things live

| Path | What |
|---|---|
| `tools/fdt.py` | DTB/DTBO reader (no libfdt), used by the other tools |
| `tools/extract-dt.py` | pull `jellystar.dtb` + `dtbo.img` out of `vendor_boot.img` |
| `tools/check-facts.py` | verify `soc.args` against those files; green or it is a bug |
| `tools/diff-port.py` | regenerate `docs/jellystar/diff-vs-x676c.md` against a HelioDarwin checkout |
| `tools/docs-gen.py` | make `docs/devices/jellystar.md` from `devices/jellystar/device.conf` |
| `devices/jellystar/` | the facts (`soc.args`) and the status (`device.conf`) |
| `docs/jellystar/` | the plan and the generated delta |
