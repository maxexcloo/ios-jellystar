# Notes

Newest first. One entry per milestone, with the kernel and image hashes and what the panel actually showed.

## 2026-11-06 — recon done on the phone: panel and touch identified

Read a Jelly Star directly (serial redacted, in `recon/`), rooted Android 13 GSI
(`TrebleDroid with GApps`, `tdgsi_arm64_ab`, `ro.boot.hardware=mt6789`, active slot `_a`,
`verifiedbootstate=orange`, `flash.locked=0`). `adb root` was required: as `shell`, `/proc/device-tree` is
`EACCES`. `tools/recon.sh` reproduces all of it.

**The panel question is closed, and the device tree lies about it.**

- Bound driver, from `lsmod`: **`panel_ST7701S_Z30043`** (`mtk_panel_ext` in use by it). That is the dtbo's
  `zhunyi,st7701,vdo` candidate — **not** `truly,td4330,cmd`. **Video mode.**
- Geometry: `card0-DSI-1/modes = 480x854`, SurfaceFlinger `480x854 @ 60.00 Hz`, `wm density 220`.
- But `/chosen/atag,videolfb-lcmname` still says `nt36672e_fhdp_dsi_vdo_60hz_jdi_dphy_drv` (a 1080×2400
  Novatek part), and the packaged Lineage DTB's framebuffer is `0x7e605000`+`0x1be0000` while the phone
  says `0xffb0c000`+`0x4c0000`. **The packaged DTB is not the one LK boots with**, and its panel name
  cannot be used to pick a driver. Had this been trusted, a TD4330 or NT36672E driver would have been
  written against a panel that is not there.
- Video mode is good news: the DSI scans out continuously, so no per-frame kick like the X676C ili7835
  command-mode panel needs (`x676c/shim/display.c`).

**Touch is Chipsea, confirmed.** `lsmod` → `chsc5xxx_touch`; `/sys/bus/i2c/devices/0-002e/name` →
`cap_touch`; `/proc/bus/input/devices` → `cap_touch` at `11e00000.i2c/i2c-0/0-002e`, `event2`. The vendor
driver logs `[CHSC]` lines (`semi_touch_suspend_entry`, ...) — that is the string to grep when recovering
its protocol from the `.ko`. No XNU driver exists for it in either MT6789 port.

**Memory.** `/proc/device-tree/memory/reg` is `0x40000000`+`0x20000000` — LK's own 512 MiB view, useless
for XNU. The reserved nodes give the real shape: `mblock-1-dramc-rk0` = `0x13ffff000`,
`mblock-2-dramc-rk1` = `0x23ffff000`, `MemTotal` 7,960,428 kB. That matches the X676C layout, so
`0x140000000`+`0xffff0000` is very likely right — but it stays **inferred** until the shim prints the live
DTB.

**pstore is identical to X676C.** `mblock-10-pstore` = `0x48090000`+`0xe0000`, so HelioDarwin's ramoops
addresses (`0x4811f000`+`0x40000` console) should work unchanged.

**Framebuffer sizes disagree with each other.** `/chosen` vram is `0x4c0000` (4.75 MiB) but
`mblock-13-framebuffer` is `0x4f3000` (19,472 bytes more) at the same base. The shim must bounds-check
against the reserved size, not the chosen one.

**Storage.** UFS LUN `sdc`, 512-byte sectors. `userdata` = 239,034,336 sectors = **228.0 GiB** (plenty for
an `iosroot` carve), `super` = 9.0 GiB, `boot_a`/`boot_b` 64 MiB each, `dtbo` 8 MiB, `metadata` 32 MiB,
`vbmeta_a/b` 8 MiB (oddly large for a real vbmeta — verify before relying on it). Both slots exist:
`boot_a` is the running Android, `boot_b` is free.

### What changed in the repo

- `devices/jellystar/soc.args`: 37 facts now re-derived from the DT, plus the phone-verified values
  (panel driver/mode, touch driver/input node, framebuffer, pstore, partition geometry). Two entries are
  reported as `PHONE` by `tools/check-facts.py` because the packaged DTB disagrees with the phone — that
  divergence is now asserted on purpose rather than papered over.
- `tools/recon.sh` added: the whole read-only recon, repeatable, output to `recon/` (git-ignored).
- `device.conf`: display and touch now carry the identified part instead of "unresolved". Both are still
  `missing` — knowing the part is not a driver.

### Next

Step 2 in `docs/jellystar/port-plan.md`: a shim on `boot_b` that prints and halts. Still unproven and the
first thing that touches the phone: whether Unihertz's LK loads an XNU payload at all, whether
`fastboot boot` works, whether `boot_b` alone suffices. Before that, capture the LK log
(`dd if=/dev/block/by-name/expdb`) and a `dmesg` with the `chsc5xxx` probe lines, which had already
scrolled away.
