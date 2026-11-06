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
| Panel | ST7701S (`vdo`) **or** TD4330 (`cmd`), 480×854 | ili7835 1080×2400 cmd | ❌ new driver |
| LK framebuffer | `/chosen/atag,videolfb-fb_base_l` = **`0x7e605000`**, vram 0x01be0000 (~29 MiB) | `0xfeabe000` | ⚠ phone |
| DRAM window | base DT says `0x40000000`+1 GiB — **stale, ignore** | rank-1 `0x140000000` | ⚠ phone |
| Boot slot | virtual A/B, real `boot_b`, recovery inside `vendor_boot` | `boot_a` via rooted Android | different |

### Three facts that decide the work

**1. The panel in the DT is not the panel on the phone.** The base DTB's `/chosen/atag,videolfb-lcmname`
says `nt36672e_fhdp_dsi_vdo_60hz_jdi_dphy_drv` — a 1080×2400 Novatek panel that cannot be fitted to a
3-inch 480×854 phone, and `vramSize` 0x01be0000 (~29 MiB) is sized for 1080×2400 buffers. The base tree
is shared across a family of MT6789 boards. The **overlay** then adds two panels to `dsi0` at once:
`zhunyi,st7701,vdo` (fragment@13 panel1) and `truly,td4330,cmd` (panel2), and the vendor ramdisk ships
panel modules for both plus six other panels (`panel-ST7701S_Z30043.ko`,
`panel-truly-td4330-cmd.ko`, NT37801, S68FC01, Tianma R66451, ...). The Lineage tree's own `kernel/README.md`
says outright: *"only one panel driver is actually relevant to Jelly Star specifically, not yet
identified which."*
→ **The first task is `adb shell cat /proc/device-tree/chosen/atag,videolfb-lcmname` on a running phone
(or `dmesg | grep -i lcm`), not writing a driver.** Getting this wrong means writing two.

**2. Touch is a Chipsea part nobody has written an XNU driver for.** Both existing MT6789 ports drive
FocalTech (`FT5452J`, `FTS3519`). The Jelly Star's `cap_touch@38` is `chipsemi` — Chipsea — and the vendor's
own Android driver is `chsc5xxx_touch.ko` in the vendor ramdisk. Note also `reg = 0x2e` (not 0x38), IRQ
GPIO 9, reset GPIO 152, and `use-tpd-button` with three capacitive keys mapped through `tpd-key-local`
(158/172/580 = back/home/recents). The protocol has to be recovered from that module (strings, ioctl paths,
register reads under Android's `dmesg` with the vendor driver loaded) — this is the single largest piece
of unknown work in the port.

Watch out for two decoys in the base DTB: `/touch_panel` says `compatible = "goodix,touch"` and `/touch`
says `mediatek,touch`. Neither has a `reg`, an interrupt or a bus — they are header stubs that the MediaTek
touch glue uses to carry phandles. They are **not** the fitted controller, and a
Goodix driver would be wasted work.

**3. 480×854 is not a phone-shaped screen for iOS.** iOS assumes an iPhone. HelioDarwin handles this the
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

- **`fastboot boot` does not work on MTK LK.** Everything is a slot flash. Good news: the Jelly Star is
  **virtual A/B with a real `boot_b`**, so Android can stay bootable on `_a` while `boot_b` holds the
  XNU shim. That is strictly safer than the `ios-redmi` plan (which overwrites `userdata` and hopes).
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

Untested here and to be treated as risk: whether Unihertz's LK will accept a boot image whose kernel is
XNU (HelioDarwin's X676C LK wants a gzip `Image` in a v4 image and rejects `fastboot boot`; the Jelly Star
is the same LK family), and whether `boot_b` alone is enough or `vbmeta`/`dtbo` also have to be staged.

## Work plan

Ordered so that each step produces evidence before the next one risks anything.

### 0. Read the phone (non-destructive)

```sh
adb shell getprop ro.board.platform                              # mt6789
adb shell cat /proc/device-tree/chosen/atag,videolfb-lcmname     # the panel actually fitted
adb shell cat /proc/device-tree/memory/reg                       # real DRAM window
adb shell dmesg | grep -iE "lcm|panel|chsc|touch|DRAM|rank"      # resolved panel + touch probe
adb shell wm size; adb shell wm density
adb shell cat /proc/device-tree/reserved-memory/*/reg            # pstore / carve-outs
# rooted: dd if=/dev/block/by-name/expdb of=expdb.bin            # LK's own boot log
# rooted: dmesg while the vendor chsc5xxx driver is loaded        # touch protocol
```

Output lands in `recon/` (git-ignored: live DT carries the serial).

### 1. Device-integrity files

`devices/jellystar/soc.args` (done) and `device.conf` (done) are checked by `tools/check-facts.py`.
Fill the *phone* rows above from step 0 and re-run it; the plan is only as good as that check.

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
