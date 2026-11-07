# iOS Jelly Star

Experimental iOS 16 / XNU bring-up for the Unihertz Jelly Star (MT6789 / Helio G99). Based on the same-SoC [HelioDarwin](https://github.com/squeeeezy/HelioDarwin) port.

## Status

**No custom code has executed on the local phone.** The Android-default chainloader builds and passes offline checks. An explicit one-shot XNU payload path is now prepared for offline builds; neither path has run on the Jelly.

| Area           | Evidence & Remaining Work                                                                                |
| -------------- | -------------------------------------------------------------------------------------------------------- |
| Boot           | The slot-B attempt could not execute; Android-default v4 chainloader built, LK loading/fallback untested |
| Display        | ST7701S timings identified; Jelly-sized XNU early console prepared; scanout untested                     |
| Touch          | Vendor-grounded 28-byte CHSC decoder host-tested; no I2C/XNU driver; reset-time firmware unresolved      |
| XNU & storage  | Pinned MT6789 kernel pipeline, Jelly ADT and mockfs PID 1 payload prepared; no partition selected        |
| Other hardware | No locally established GPU, networking, audio, camera, sensors or power-management support               |

## Build & Check

Host tools use Python 3.11+ (activated by Mise), its standard library and a C compiler. Native builds need LLVM (`clang`, `ld.lld`, `llvm-objcopy`, `llvm-nm`, `llvm-readelf`). The builder recognises Homebrew's keg-only LLVM directory; `CC`, `LD`, `OBJCOPY`, `NM` and `READELF` can select explicit executables.

```sh
mise run check
mise run build -- recon/backup/boot_a.img
```

The output is `out/chainboot/chainboot.img`. The builder embeds the complete saved Android Image at an aligned offset, preserves its appended data, generic ramdisk and unaffected boot-v4 fields, and omits invalidated signatures. Tests cover image preservation, deterministic packing, one-shot triggers and live framebuffer selection. Offline checks do not establish Android fallback.

## Offline XNU Experiment

`xnu/sources.toml` pins HelioDarwin, the XNU builder and Apple's XNU 8796.141.3 source. Third-party source is fetched into ignored `out/`; no upstream drivers are vendored. The XNU workflow builds and links `DEVELOPMENT/ARM64/SWEET` on Xcode 16 and uploads a kernel only after the upstream assembled-startup check passes. It publishes no boot image or Apple/vendor inputs.

```sh
mise exec -- python tools/prepare-kernel.py
mise exec -- python tools/build-init.py
mise exec -- python tools/build-payload.py PATH_TO_JELLY_KERNEL
mise run build -- recon/backup/boot_a.img --out out/xnu/boot --xnu-payload out/xnu/payload.bin
```

Preparation fetches sources; `prepare-kernel.py --build` additionally invokes the macOS/Xcode builder. The CI artifact is `jellystar-xnu`. Use its Jelly kernel, not an unmodified Infinix kernel: the local patch changes the unconditional early framebuffer addresses, row stride, marker bounds and pstore console mapping. Generated constants come from `shim/soc.args` and the saved live DT/ramoops layout. The common MT6789 board guard prevents Qualcomm battery MMIO. The ADT describes one A55 CPU, GICv3, the 13 MHz virtual timer and the 480×854 framebuffer; it omits the Infinix DSI, GPU, touch and UFS service nodes.

The signed static test `init` uses XNU's existing mockfs `rd=md0` path: its executable bytes become `/sbin/launchd`, without an HFS+ image or partition. It writes diagnostic messages and exercises userspace syscalls; it is not iOS userland. Native `codesign --verify --strict` checks the executable without running it.

Only an image built with `--xnu-payload` recognises `JELLYSTAR:XNU` in pmsg. It consumes the marker before loading, verifies payload bounds and the matching live framebuffer reservation, and accepts only boot CPU 0 at EL1 with MMU/data cache already off. Unsupported handoffs return to Android before copying XNU. A valid request loads the kernel, ADT and revision-2 boot arguments into the verified high-memory window. Once entered, XNU does not return to Android; a consumed marker cannot reset a hang. Without the marker, the inherited Android handoff remains the default. No experiment is authorised by building its image.

`tools/touch-report.py REPORT.bin` decodes a saved 28-byte CHSC report. Disassembly of the local vendor module establishes five five-byte records (not the DT's ten-contact maximum), 12-bit coordinates, slot/event fields and report address `0x2000002c` sent big-endian before a repeated-start read. Tests use synthetic reports; no real report, reset sequence or volatile-firmware requirement has been validated.

`tools/build-root.py BuildManifest.plist --check-inputs` resolves locally supplied D22AP 16.7.16 / 20H392 OS and cryptex images. Its optional full macOS build creates a standalone HFS+ image, preserves numeric ownership, links cryptex content, applies pinned root tweaks and invalidates MobileGestalt's hardware cache. It needs host root privileges and does not choose or provision a Jelly partition. Camera/flash must remain unadvertised until media services work; replacing a loaded signed executable requires rename. The full root image has not been built here.

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

Apple's XNU and the local patches to it use APSL 2.0. HelioDarwin's original tooling uses its MIT licence, retained in the pinned dependency; its XNU patches retain APSL provenance. KLiOS716 (`318f265a7e975cc12ef4bfe063ad029026e90105`) and HakiOS (`4711c19068e5bb8b1ff6898e83add5392e40dd61`) were inspected as secondary root/chainloading references; their code is not imported. The repository LICENSE remains unchanged.
