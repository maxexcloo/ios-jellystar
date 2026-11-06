# iOS on the Unihertz Jelly Star — port plan

Branch `jellystar`. Target: Unihertz Jelly Star (`jellystar`, MediaTek **MT6789 / Helio G99**), 8 GiB
RAM, 256 GiB UFS 2.2, 3.0" 480×854 LCD, Mali-G57 MC2, Android 13 shipped / Android 16 from Unihertz.

Started 2026-11-06. **Nothing has run on a phone.** This page is the plan and the evidence behind it.

## Why this target is unusually cheap

The expensive half of an XNU bring-up on Android silicon is the SoC layer: GICv3, the generic timer,
storage, the display controller, the PMIC access path and the GPU. All of that is already written for
MT6789 by two independent projects:

| Project | Device | State | Use it for |
|---|---|---|---|
| **`squeeeezy/HelioDarwin`** | Infinix Note 12 2023 (X676C), MT6789, Mali-G57 | 208 patches. Boots to `launchd`, SpringBoard and `backboardd`; the panel shows the clock; touch and keys reach kernel HID; GPU power-on and JM job completion confirmed; native Vulkan device created. UI still software-rendered | **The base.** Address-for-address the same SoC |
| `lib-fluff-so/KLiOS716` + `-shim` | TECNO Spark 30 Pro (KL7), MT6789, Mali-G57 | 129 patches, reaches the lockscreen on `boot_b`, dual-boots Android on `_a`. Own SweetMali driver + Mesa/panfrost userspace | Second opinion, and the **boot/recovery discipline** this plan copies |
| `MakrSas/ios-topaz` | Redmi Note 12 (MT6789) | Upstream of HelioDarwin | history |
| `UniXNU/UniXNU` → `woaphone/UniXNU-yunluo` | Redmi Pad, MT6789 | components only, no boot | not useful |

There is **no** iOS/XNU port for the Jelly Star, and none for any Unihertz device, on GitHub as of
2026-11-06. What exists for this phone is Android: `osquera/lineageos_unihertz_jellystar` (LineageOS
23.2), `dnlzro/android_device_unihertz_jelly_star` (AOSP 16), `KawashiroDev/twrp_device_unihertz_jellystar`
(TWRP). Those matter here because they carry the stock `vendor_boot`/`dtbo` this plan reads, and because
the Lineage maintainer's notes are the best public record of how the boot chain behaves.

`tools/diff-port.py` prints the whole delta against HelioDarwin, with `file:line` for each constant:
**16 unchanged, 9 constants, 4 new drivers.**

## Hardware, read from the phone's own device tree

Source: `osquera/lineageos_unihertz_jellystar` release `20261101`, `vendor_boot.img` (header v4) and
`dtbo.img`. Extract with `tools/extract-dt.py vendor_boot.img dtbo.img --out fw`; check with
`tools/check-facts.py`, which re-reads those files and fails if `devices/jellystar/soc.args` drifts.

Everything in this table is verified against the DT except the rows marked *phone* (they need the phone
in hand) and *Android* (they come from the Lineage tree, not the DT).

| Item | Jelly Star | X676C (working) | |
|---|---|---|---|
| GICD / GICR | `0x0c000000`+0x40000 / `0c040000`+0x200000 | same | ✅ |
| Generic timer | 13 MHz, PPI 11 → INTID 27 | same | ✅ |
| CPUs | 6× A55 @0x000–0x500, 2× A76 @0x600/0x700 | same | ✅ |
| Page size | 16 KiB | 16 KiB | ✅ |
| UFS host | `0x11270000`+0x2300, SPI 137, resets via infracfg_ao | same | ✅ |
| DSI0 / DISP_MUTEX0 | `0x14013000` SPI 301 / `0x14001000` SPI 285 | same | ✅ |
| Mali GPU | `0x13000000`+0x4000, SPIs 396/397/398/399/400 (`arm,mali-valhall`) | same | ✅ |
| MFG_TOP_CFG | `0x13fbf000` | same | ✅ |
| TOPCKGEN / INFRACFG_AO / GPIO / SPM | `0x10000000` / `10001000` / `10005000` / `10006000` | same | ✅ |
| PWRAP → MT6366 | `0x10026000` | same | ✅ |
| TOPRGU | `0x10007000`, restart `+0x08`, key `0x1971` | same | ✅ |
| Volume keys | `kp@10010000`, SPI 106 | same | ✅ |
| Power key | MT6366 `keys/power` = code 116, `keys/func2` = code 250; **red shortcut key = keypad scan code 249** (Lineage `mtk-kpd.kl`) | same PMIC, no func2 | ✅ |
| Touch | **Chipsea `chsc5xxx`**, i2c0 `11e00000` @ **0x2e**, 400 kHz, IRQ GPIO 9 (type 2), reset GPIO 152, 10 touches, 480×854 | FocalTech FT5452J @ 0x38 | ❌ new driver |
| Panel | **ST7701S (`panel_ST7701S_Z30043`), video mode, 480×854 @ 60 Hz** — verified | ili7835 1080×2400 cmd | ❌ new driver |
| LK framebuffer | `/chosen` = **`0xffb0c000`**, vram 0x4c0000; carve-out `mblock-13-framebuffer` = `0xffb0c000`+0x4f3000 — verified | `0xfeabe000` | ⚠ sizes disagree |
| DRAM window | `mblock-1-dramc-rk0` = `0x13ffff000`, `mblock-2-dramc-rk1` = `0x23ffff000` — verified | rank-1 `0x140000000`+0xffff0000 | ⚠ inferred |
| pstore | `mblock-10-pstore` = `0x48090000`+0xe0000 — verified, **identical to X676C** | `0x48090000`+0xe0000 | ✅ |
| Boot slot | virtual A/B; `boot`, `vendor_boot`, `dtbo`, `vbmeta` are slotted; recovery inside `vendor_boot` | `boot_a` via rooted Android | different |

### The recon questions are answered (2026-11-06)

The phone was read directly (rooted Android 13 GSI, `adb root`). Every "phone" row above is now measured,
not inferred. `/proc/device-tree` needs root; as `shell` it is `EACCES`.

**1. Panel: ST7701S, video mode. Settled, and `/chosen` lies.** `lsmod` shows
`panel_ST7701S_Z30043` bound (`mtk_panel_ext` in use by it), which is the overlay's
`zhunyi,st7701,vdo` candidate — *not* the TD4330 command-mode one. DRM reports
`card0-DSI-1/modes = 480x854` and SurfaceFlinger `480x854 @ 60.00 Hz`.

Yet `/chosen/atag,videolfb-lcmname` still says `nt36672e_fhdp_dsi_vdo_60hz_jdi_dphy_drv`, a 1080×2400
Novatek part. **So the chosen lcmname cannot be used to pick a panel driver on this phone** — a trap that
would have cost a wasted driver, since the packaged DTB and the live one disagree. Video mode also means
the DSI scans out continuously and needs no per-frame kick, unlike HelioDarwin's command-mode ili7835.
→ **The first task is `adb shell cat /proc/device-tree/chosen/atag,videolfb-lcmname` on a running phone
(or `dmesg | grep -i lcm`), not writing a driver.** Getting this wrong means writing two.

**2. Touch is a Chipsea part nobody has written an XNU driver for — confirmed.** Both existing MT6789 ports drive
FocalTech (`FT5452J`, `FTS3519`). The Jelly Star's `cap_touch@38` is `chipsemi` — Chipsea — and the vendor's
own Android driver is `chsc5xxx_touch.ko` in the vendor ramdisk. Note also `reg = 0x2e` (not 0x38), IRQ
GPIO 9, reset GPIO 152, and `use-tpd-button` with three capacitive keys mapped through `tpd-key-local`
(158/172/580 = back/home/recents). The protocol has to be recovered from that module (strings, ioctl paths,
register reads under Android's `dmesg` with the vendor driver loaded) — this is the single largest piece
of unknown work in the port.

Confirmed on the phone: `lsmod` has `chsc5xxx_touch`, `/sys/bus/i2c/devices/0-002e/name` is `cap_touch`,
and `/proc/bus/input/devices` shows `cap_touch` at `11e00000.i2c/i2c-0/0-002e` as `event2`. The vendor
driver prints `[CHSC]` lines (e.g. `semi_touch_suspend_entry`), which is the string to grep when recovering
its protocol from the `.ko`.

Two decoys in the base DTB, ignore both: `/touch_panel` says `compatible = "goodix,touch"` and `/touch`
says `mediatek,touch`. Neither has a `reg`, an interrupt or a bus — they are header stubs carrying phandles.
A Goodix driver would be wasted work.

**3. The framebuffer base differs from the packaged DTB, and two sizes disagree.** The phone says
`/chosen` = `0xffb0c000`, vram `0x4c0000` (4.75 MiB); reserved-memory `mblock-13-framebuffer` says the same
base but `0x4f3000` (19,472 bytes more). The packaged Lineage DTB says `0x7e605000`/`0x1be0000` — i.e. that
DTB is *not* the one LK boots with. `readelf` cannot help here: the shim must read the live DTB (as
HelioDarwin's `loader.c` already does) and bounds-check writes against the reserved size.

**4. DRAM looks like the X676C layout, but is still inferred.** `/proc/device-tree/memory/reg` is
`0x40000000`+`0x20000000` — a 512 MiB window at 1 GiB, which is LK's own view and useless for XNU. The
reserved nodes give the real shape: rank 0 ends at `0x13ffff000`, rank 1 at `0x23ffff000`, and
`MemTotal` is 7,960,428 kB (7.59 GiB) — two 4 GiB ranks minus carve-outs, exactly as on X676C. So
`0x140000000`+`0xffff0000` is very likely right, but it stays **INFERRED** until the shim prints the live
DTB. Cheap to confirm, so confirm it first.

**5. 480×854 is not a phone-shaped screen for iOS.** iOS assumes an iPhone. HelioDarwin handles this the
way every port does: publish an iPhone canvas to the ADT (`display-scale`, `canvas-width/height`) and let
the framebuffer path scale. At 480×854 the honest options are:

- canvas 480×854, `display-scale` 2 → 240×427 pt logical. Every UIKit control is ~2.3× smaller than the
  smallest iPhone; hits are ~20 px. Text is legible, tapping is not.
- canvas 1125×2436 scaled down to 480×854 → correct *layout*, unreadable text, and a scaler is more code.

Recommendation: build **480×854 native, scale 2** first (fewer moving parts, and it is what the panel
really is), then try a scaled canvas only if the UI is unusable. Do not treat the canvas size as a
solvable problem — it is a 3-inch screen.

## Boot and recovery: what is safe on this phone

Copied from the Lineage and KLiOS716 notes, because both were learned on hardware:

- **`fastboot boot` is expected to be rejected, and untested on this phone.** Everything is assumed to be a
  slot flash. The Jelly Star is **virtual A/B** (`AB_OTA_UPDATER`, slots for `boot`, `vendor_boot`, `dtbo`,
  `vbmeta`; the Lineage notes rely on Magisk's "install to inactive slot"), so in principle Android can stay
  bootable on `_a` while `boot_b` holds the XNU shim. That is the intended safety model — but *whether
  Unihertz's LK accepts `fastboot boot` at all, and whether a separate `boot_b` accepts a non-Android kernel*,
  has not been confirmed here. Check with `fastboot getvar current-slot` / `fastboot getvar slot-count`
  before designing around it. It is still strictly safer than the `ios-redmi` plan (which overwrites
  `userdata` and hopes).
- **Never flash `boot_a`, never relock the bootloader.** Unihertz's LK only trusts Unihertz's signing key
  and there is no `avb_custom_key`, so a relocked phone refuses to boot a modified image, and unlocking
  again needs a booting Android.
- **Recovery lives inside `vendor_boot`** (`BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT`), and Unihertz's
  LK insists on a separate recovery ramdisk fragment — otherwise recovery halts with
  `ASSERT FAILED at (app/mt_boot/boot_info.c:333)`.
- **Unbrick = SP Flash Tool v6 + stock Android 16 firmware**, "Firmware Upgrade" or "Download Only",
  **never "Format All + Download"** (that erases IMEI and calibration). Tested by the Lineage maintainer.
  Power off, hold Volume Up + Volume Down, plug in.
- **Anti-rollback blocks the original Android 13 firmware.** Back to stock means Android 16 firmware.
- Unihertz **publishes no kernel source**, so nothing can be read from vendor source: the panel and touch
  init have to come from the vendor modules and from observation.

Untested here, and to be treated as risk rather than assumption:

- whether Unihertz's LK accepts a boot image whose kernel is XNU at all — the X676C LK wants a gzip `Image`
  in a v4 image, and the Jelly Star is the same LK family;
- whether `fastboot boot` works (X676C's LK rejects it);
- whether writing `boot_b` alone is enough, or `vbmeta`/`dtbo` also have to be staged to satisfy verified
  boot.

All three are answered by step 2, which is deliberately the cheapest thing that touches the phone.

## Work plan

Ordered so that each step produces evidence before the next one risks anything.

### 0. Read the phone — DONE 2026-11-06

Done on a rooted Android 13 GSI (`adb root`; as `shell`, `/proc/device-tree` is `EACCES`). What was
learned is in the table above and in "the recon questions are answered". The panel and touch questions are
closed; DRAM is the one open item.

Re-run any of it with `tools/recon.sh` (writes to `recon/`, git-ignored — the live DT carries the serial).

Still worth collecting before step 2: the LK boot log (`dd if=/dev/block/by-name/expdb`, root), and a
`dmesg` capture with the vendor `chsc5xxx` driver's probe lines (they were already past by the time recon
ran, since `dmesg` only holds the last few minutes here).

### 1. Device-integrity files — DONE

`devices/jellystar/soc.args` and `device.conf` are checked by `tools/check-facts.py`: 37 facts re-derived
from the DT, 2 reported as `PHONE` where the packaged DTB disagrees with the phone (the framebuffer), 19
skipped because the fact does not live in the DT. Keep it green.

### 2. Shim bring-up, no XNU

Port `HelioDarwin`'s `x676c/shim` to print and halt:
`TOPRGU_BASE`/`WDT_RESTART`, PSCI, the live FDT parse, and the framebuffer console at
`atag,videolfb-fb_base_l`. Success = text on the panel, `HANDOFF` echoed, and the phone returns to
Android after a power cycle. This is the cheapest possible test of "does Unihertz's LK load our image".
Flash to **`boot_b`** only.

### 3. XNU to `launchd`

Reuse HelioDarwin's patch train as-is with the constants from `tools/diff-port.py` changed (RAM window,
framebuffer geometry, ECID/chip-id synthetics, pstore reservation, `compatible` strings). The expected
first milestone is `launchd` + `backboardd` with the panel showing whatever the shim left, i.e. what
X676C reached months ago, then the MTK display path takes over.

### 4. Display

Only after step 0 names the panel: port the DSI init sequence for ST7701S (video mode) or TD4330 (command
mode) out of the vendor panel module, with the 480×854 timings. HelioDarwin's `0190` (serialise the DSI
refresh) and `0177` (native DSI vsync) are the shape to copy; command-mode and video-mode need different
handling, which is why guessing the panel is expensive.

### 5. Touch

New I2C HID driver: `chsc5xxx` at 0x2e on `i2c@11e00000`, GPIO 9 interrupt, GPIO 152 reset, 10 contacts,
480×854 coordinates, three capacitive keys as HID consumer/button usages. Copy the structure of
HelioDarwin's `0175`/`0192`/`0194` (register access, report parse, diagnostics) and replace the protocol.

### 6. After that

Buttons (`0175` keypad + MT6366 keys; note the Jelly Star's **red shortcut key is keypad scan code 249**
and the capacitive keys are 158/172/580), battery (MT6366 gauge), GPU (HelioDarwin's Mali train, including
`MaliMetal`), USB/MUSB if useful for logs, then the rest.

## Not worth attempting

- **Wi-Fi/Bluetooth**: `consys@18002000` — MediaTek's connectivity subsystem, Wi-Fi and BT behind a firmware
  blob on an internal DSP. No XNU driver exists for any MediaTek Wi-Fi, on any port. Eth-over-USB is the
  sane debug path.
- **Camera, sensors, NFC, cellular, audio**: vendor-DSP territory, nothing reusable.
- **The lights** (front RGB LED, back LED belt, red shortcut key): vendor kernel modules, cosmetic.
- **Fastboot boot**: LK refuses it (same family as X676C).

## Honest expectation

- "Text on the panel from our own image" is a day or two of work if the LK cooperates.
- "`launchd` runs iOS from `userdata`" is the X676C patch train plus ~9 constants — plausible in a week of
  evenings, blocked mainly on step 0.
- "SpringBoard on the glass, touch works" needs both new drivers. The touch one has no reference anywhere.
- "Usable phone" — no. 480×854 kills it before the missing radios do.

Nothing here changes the standing rule for this repository: an item moves from `missing` in
`devices/jellystar/device.conf` only when the phone showed it.
