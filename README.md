# iOS Jelly Star

Experimental iOS 16 / XNU bring-up for the Unihertz Jelly Star (MT6789 / Helio G99). Based on the same-SoC [HelioDarwin](https://github.com/squeeeezy/HelioDarwin) port.

## Status

**No custom code has executed on the local phone.** The Android-default chainloader builds and passes offline checks. It does not contain an XNU payload yet.

| Area           | Evidence & Remaining Work                                                                                |
| -------------- | -------------------------------------------------------------------------------------------------------- |
| Boot           | The slot-B attempt could not execute; Android-default v4 chainloader built, LK loading/fallback untested |
| Display        | ST7701S panel and timings identified; diagnostic colour fill prepared, no XNU driver                     |
| Touch          | Chipsea `chsc5xxx` identified; no XNU driver; reset-time firmware requirements unresolved                |
| XNU & storage  | Same-SoC reference exists; kernel/ADT port and root layout not integrated here                           |
| Other hardware | No locally established GPU, networking, audio, camera, sensors or power-management support               |

## Build & Check

Host tools use Python's standard library and a C compiler. Native builds need LLVM (`clang`, `ld.lld`, `llvm-objcopy`, `llvm-nm`, `llvm-readelf`). The builder recognises Homebrew's keg-only LLVM directory; `CC`, `LD`, `OBJCOPY`, `NM` and `READELF` can select explicit executables.

```sh
mise run check
mise run build -- recon/backup/boot_a.img
```

The output is `out/chainboot/chainboot.img`. The builder embeds the complete saved Android Image at an aligned offset, preserves its appended data, generic ramdisk and unaffected boot-v4 fields, and omits invalidated signatures. Tests cover image preservation, deterministic packing, one-shot triggers and live framebuffer selection. Offline checks do not establish Android fallback.

## Device Workflow

The next hardware milestone is the Android-only chainloader. Once Android fallback is observed, build the optional one-shot colour diagnostic:

```sh
mise run build -- recon/backup/boot_a.img --out out/diagnostic --diagnostic
```

A `JELLYSTAR:DIAGNOSTIC` marker in the pmsg ring selects the diagnostic. It consumes the marker, draws within the live framebuffer reservation, waits five seconds and continues into Android. The persistent-ring location is derived from Linux 5.10 and the saved live boot arguments; trigger survival needs hardware validation. No device command is supplied before the boot/recovery experiment is reviewed with the phone present.

**Recovery:**

Slot A is this phone's only bootable Android chain. Every slot-B boot-chain partition was zero when measured; flashing `boot_b` alone fails in the preloader and eventually falls back to A. Do not provision slot B as a shortcut.

LK fastboot transfers time out on this macOS host. Android fastbootd works, but neither path supports `fastboot boot`, so no temporary RAM-only test route is established.

Before a `boot_a` experiment, retain the original boot image and verified backups of `persist`, `nvdata`, `nvcfg`, `nvram`, `proinfo` and `sec1`, and obtain Android 16 stock recovery firmware. The chainloader's Android fallback still needs a first hardware test. Restoring the saved `boot_a` through working fastbootd is the intended rollback while Android remains reachable.

The documented unbrick path is SP Flash Tool v6 with matching Android 16 stock firmware, using “Firmware Upgrade” or “Download Only”. The original Android 13 firmware is blocked by anti-rollback. Never use “Format All + Download”, which destroys calibration/IMEI, and never relock modified software.

A triggered diagnostic consumes its marker before drawing and then continues to Android. If the phone hangs before the marker is consumed, a forced restart can repeat the experiment; one-shot behaviour is not a recovery guarantee. Do not flash until the current recovery route is reviewed with the phone present.

## Inputs Kept Locally

Vendor images and modules stay in `fw/` or `recon/`; `out/` contains generated images. Apple's files, partition backups and phone logs are not committed. The board facts and their sources live in [shim/soc.args](shim/soc.args).

```sh
python3 tools/extract-dt.py vendor_boot.img dtbo.img --out fw
python3 tools/check-facts.py
```

The checker reads `fw/jellystar.dtb`, `fw/dtbo.img` and, when present, the saved `recon/live.dtb`. The packaged DT disagrees with the phone's framebuffer/panel information; the live reservation is authoritative. `tools/recon.sh` collects Android observations, and `tools/unpack-vendor-ramdisk.sh` plus `tools/panel-init.py` recover the vendor panel data.

## Credits & Licences

Original tools and Jelly Star work use the repository's [MIT licence](LICENSE). Apple, Unihertz and MediaTek binaries are supplied locally and are not redistributed.

- [HelioDarwin](https://github.com/squeeeezy/HelioDarwin): XNU on the MT6789 Infinix Note 12 2023; SoC/driver reference.
- [KLiOS716](https://github.com/lib-fluff-so/KLiOS716): another MT6789 port and boot reference; its software renderer is not GPU-accelerated UI evidence.
- [HakiOS MT6768](https://github.com/oosexgang/hakios-mt6768): Android-default MediaTek chainloader precedent; different SoC, storage and boot-image version. No loader code is vendored here.
- [ios-sweet](https://github.com/dipa-studio/ios-sweet) and [ios-topaz](https://github.com/MakrSas/ios-topaz): upstream XNU-on-Android work. Topaz is Qualcomm SM6225, not MT6789.
- [Jelly Star LineageOS](https://github.com/osquera/lineageos_unihertz_jellystar): vendor-image/recovery references.
- [Linux AArch64 boot protocol](https://docs.kernel.org/arch/arm64/booting.html), [Linux 5.10 ramoops](https://github.com/torvalds/linux/blob/v5.10/fs/pstore/ram.c) and [AOSP boot headers](https://source.android.com/docs/core/architecture/bootloader/boot-image-header): format and handoff references; no source copied.

Apple's XNU uses APSL 2.0. Upstream projects retain their own licences; this repository currently contains no XNU patch series or imported kernel drivers.
