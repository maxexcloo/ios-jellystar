# Handoff — ios-jellystar

State as of 2026-11-06. For whoever picks this up next (human or agent).

## Where this stands in one paragraph

A Jelly Star was read on the phone. The two questions that were blocking the port — which panel, which
touch controller — are **answered**. The panel is an **ST7701S in video mode at 480×854 @ 60 Hz**
(`panel_ST7701S_Z30043`), and the device tree's own panel name is **wrong**, so nobody should trust it
again. Touch is a **Chipsea `chsc5xxx`** at i2c0 `0x2e`. Neither has an XNU driver; both are new work. The
SoC layer (GIC, timer, UFS, DSI, PMIC, TOPRGU, Mali-G57) is address-identical to the working Infinix
Note 12 (X676C) port, `squeeeezy/HelioDarwin`, which is the base to fork. **Nothing has been built or
flashed for this phone.** Every subsystem in `devices/jellystar/device.conf` is still `missing`, and that
is accurate.

## What is verified vs assumed

Verified on the phone (rooted Android 13 GSI, `adb root`, 2026-11-06; re-runnable via `tools/recon.sh`):

- SoC `mt6789`; active slot `_a`; `verifiedbootstate=orange`; `flash.locked=0` → bootloader unlocked.
- Panel: `panel_ST7701S_Z30043` bound, video mode, 480×854 @ 60 Hz, density 220.
- Touch: `chsc5xxx_touch`, `/sys/bus/i2c/devices/0-002e/name` = `cap_touch`, `event2`.
- Framebuffer: `/chosen` `0xffb0c000` + `0x4c0000`; reserved `mblock-13-framebuffer` `0xffb0c000` +
  `0x4f3000` (sizes disagree — bounds-check against the reserved one).
- pstore: `mblock-10-pstore` `0x48090000` + `0xe0000` — **identical to X676C**, so HelioDarwin's ramoops
  console at `0x4811f000` should carry over.
- DRAM shape: rank0 ends `0x13ffff000`, rank1 ends `0x23ffff000`; `MemTotal` 7,960,428 kB.
- Storage: LUN `sdc`, 512-byte sectors; `userdata` 228.0 GiB, `super` 9.0 GiB, `boot_a`/`boot_b` 64 MiB,
  `dtbo` 8 MiB, `metadata` 32 MiB, `vbmeta_a/b` 8 MiB.
- CPU: 6× A55 (capacity 348) + 2× A76 (capacity 1024) — same split as X676C.

Still **assumed**, and cheap to falsify:

- **Kernel RAM window `0x140000000` + `0xffff0000`.** Inferred from the dramc reserved pages matching
  X676C, not read from the live DTB. The shim prints the live DTB, so this gets confirmed at step 2 or
  not at all. Do not build an ADT on this without the shim's output.
- **`boot_b` is a safe place for the shim.** Both slots exist and `boot_a` is running Android, so the
  intent holds — but whether Unihertz's LK will *load an XNU kernel* from `boot_b`, and whether
  `vbmeta` protests, is untested.
- **`fastboot boot` works at all.** X676C's LK rejects it; this is the same LK family. Untested here.

Beware two things in the packaged firmware that are actively misleading:

1. `/chosen/atag,videolfb-lcmname` = `nt36672e_fhdp_dsi_vdo_60hz_jdi_dphy_drv`. Wrong panel. The base DTB
   is shared across a family of MT6789 boards.
2. The packaged DTB's framebuffer (`0x7e605000` + `0x1be0000`) is not the one the phone uses. The
   **packaged DTB is not the DTB LK boots with.**

## Files, and what to trust

| Path | Trust |
|---|---|
| `devices/jellystar/soc.args` | **The fact set.** 37 facts re-derived from the DT by `tools/check-facts.py`; phone-measured values marked `(phone)`. Two rows are deliberately reported as `PHONE` divergences. |
| `devices/jellystar/device.conf` | **The only status list.** All `missing`. Move a row off `missing` only on a phone result. |
| `docs/jellystar/port-plan.md` | The plan, with the recon findings folded in. Start here. |
| `docs/jellystar/diff-vs-x676c.md` | Generated: 16 unchanged / 9 constants / 4 new drivers vs HelioDarwin, with `file:line`. |
| `docs/devices/jellystar.md` | Generated from `device.conf`. Do not edit by hand. |
| `NOTES.md` | The recon log, dated. |
| `tools/recon.sh` | Repeatable read-only recon. Needs `adb root`. |
| `tools/check.sh` | Everything checkable without a phone. Must stay green. |
| `recon/`, `fw/` | Local only, git-ignored. `recon/` holds the serial. |

`python3 tools/check-facts.py` must stay green (37 ok, 2 `PHONE`, 27 skip). `tools/check.sh` must stay
green. CI (`.github/workflows/check.yml`) runs what it can without the vendor images, including a guard that
fails if any subsystem claims `works`/`partial`.

## The next concrete step

**Step 2: a shim on `boot_b` that prints and halts.** Nothing touches flash before that.

1. Fork `squeeeezy/HelioDarwin`, branch from `x676c`.
2. Clone `lib-fluff-so/KLiOS716` alongside as the second reference — its boot discipline (`boot_b` only,
   never `boot_a`, how to come back) is what this phone needs.
3. Change the constants `tools/diff-port.py` lists: framebuffer `0xffb0c000`/`0x4f3000`, panel
   `480x854` + `panel_ST7701S_Z30043` (video mode, so no per-frame kick), ECID/chip-id synthetics,
   `compatible` strings to `unihertz,jellystar`, pstore unchanged.
4. Let the shim parse the **live** DTB (HelioDarwin's `loader.c` already does) and print the RAM window it
   found. That single output either confirms `0x140000000`+`0xffff0000` or corrects it.
5. `fastboot flash boot_b`, boot, and expect text on the panel or a clean return to Android.

Before flashing anything, capture: `dd if=/dev/block/by-name/expdb` (LK's own boot log, which records what
it did with the image) and a `dmesg` with the `chsc5xxx` probe lines — they had already scrolled out of the
ring when recon ran.

## Things not to do

- Do not flash `boot_a`, do not relock the bootloader, do not use "Format All + Download" in SP Flash
  Tool (erases IMEI/calibration). Unbrick path: SP Flash Tool v6 + **Android 16** firmware, "Firmware
  Upgrade" or "Download Only". The original Android 13 firmware cannot be flashed (anti-rollback).
- Do not write a panel driver from `/chosen`'s lcmname. It is wrong on this phone.
- Do not assume the touch protocol from FocalTech; the part is Chipsea.
- Do not treat "the DT says so" as "the phone does it". That is exactly the failure this recon caught.

## Open questions worth answering before much code is written

- Which panel IC init sequence does `panel_ST7701S_Z30043` actually send? It is in the `.ko` in
  `vendor_ramdisk00` (LZ4 legacy frames, see the Lineage tree's `kernel/README.md`), and the module is
  small enough to disassemble.
- Does `chsc5xxx` expose a plain register-read protocol over i2c, or does it need firmware download first?
  Check for a `.bin` in `/vendor/firmware` and strings in the `.ko`.
- Does the panel run at 60 Hz only, or is there a timing table with alternatives? One mode is all
  `card0-DSI-1/modes` reported, which simplifies iOS's display-mode handling.
