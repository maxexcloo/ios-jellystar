# iOS Jellystar

Experimental iOS 16 / XNU 8796.141.3 bring-up for the Unihertz Jelly Star (jellystar, MT6789 / Helio G99), based on the same-SoC [HelioDarwin](https://github.com/squeeeezy/HelioDarwin) port.

## Status

**No custom code has executed on the local phone.** The Android-default chainloader and the one-shot XNU image build and pass offline checks; [the full XNU compile, link and startup check passed in CI](https://github.com/maxexcloo/ios-jellystar/actions/runs/42343509125). LK loading, Android fallback, pmsg survival, XNU entry, console pixels and userspace syscalls remain physically untested.

| Area           | Evidence & Remaining Work                                                                                                        |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Boot           | The slot-B attempt could not execute; Android-default v4 chainloader built, LK loading/fallback untested                         |
| Display        | Opt-in native 480×854 IOMFB/IOSurface CPU-copy path compiled; no DSI, OVL, GPU, PMIC, brightness or panel-power programming      |
| Touch          | Opt-in CHSC I2C/APDMA polling/HID path compiled and host-tested; no reset pulse, firmware upload or EINT; bus and touch untested |
| XNU & storage  | Jelly XNU linked; ADT/mockfs PID 1 payload and 27 MB image built; storage unselected                                             |
| Root           | D22AP 16.7.16 (20H392) inputs resolve and mount read-only; full HFS+ root build needs host `sudo` and remains unexercised        |
| Other hardware | No locally established GPU, networking, audio, camera, sensors or power-management support                                       |

## Build & Check

Host tools use Python (activated by Mise), its standard library and a C compiler. Native builds need LLVM (`clang`, `ld.lld`, `llvm-objcopy`, `llvm-nm`, `llvm-readelf`); Homebrew's keg-only LLVM is recognised, and `CC`, `LD`, `OBJCOPY`, `NM` and `READELF` select explicit executables.

```sh
mise run check
mise run build -- recon/backup/boot_a.img
```

The build writes `out/chainboot/chainboot.img`, embedding the complete saved Android image with its appended data, generic ramdisk and unaffected boot-v4 fields, and omitting invalidated signatures. `--diagnostic` adds the one-shot colour diagnostic; `--xnu-payload PAYLOAD` adds the one-shot XNU experiment.

`xnu/sources.toml` pins HelioDarwin, darwin-xnu-build and Apple's XNU; sources are fetched into `out/sources/`. The XNU workflow builds `DEVELOPMENT/ARM64/SWEET` on Xcode 16 and uploads the `jellystar-xnu` artefact after the startup check passes; run it manually with `gh workflow run xnu.yaml --ref main`. Use that Jelly kernel, not an unmodified Infinix kernel: the local patches change the early framebuffer, marker bounds and pstore console mapping.

```sh
python tools/prepare-kernel.py  # --build runs the macOS/Xcode builder
python tools/build-init.py
python tools/build-payload.py PATH_TO_JELLY_KERNEL  # add --display and/or --touch
mise run build -- recon/backup/boot_a.img --out out/xnu/boot --xnu-payload out/xnu/payload.bin
```

The default payload is a minimal smoke test: one A55 CPU, GICv3, the 13 MHz virtual timer and the framebuffer, with a signed static test `init` booted through mockfs `rd=md0`. `--display` and `--touch` each add their own ADT node; without them neither service starts.

Run as root, `python tools/build-root.py BuildManifest.plist` builds a standalone HFS+ root from locally supplied D22AP images, preserving numeric ownership and invalidating MobileGestalt's hardware cache; `--check-inputs` only resolves the images. It does not choose a Jelly partition.

## Device Workflow

The next hardware milestone is the Android-only chainloader. Once Android fallback is observed, build the colour diagnostic:

```sh
mise run build -- recon/backup/boot_a.img --out out/diagnostic --diagnostic
```

A `JELLYSTAR:DIAGNOSTIC` marker in the pmsg ring selects it: the loader consumes the marker, draws within the live framebuffer reservation, waits five seconds and continues into Android. Only an image built with `--xnu-payload` recognises `JELLYSTAR:XNU`; it consumes the marker, validates the payload, the framebuffer reservation and an EL1 boot CPU 0 handoff with MMU and data cache off, and otherwise returns to Android. Once entered, XNU does not return to Android. Without a marker, the Android handoff is unchanged. Building an image authorises no experiment.

**Recovery:**

Slot A is the only bootable Android chain. Every slot-B boot-chain partition was zero when measured, and flashing `boot_b` alone fails in the preloader before falling back to A; do not provision slot B as a shortcut. LK fastboot transfers time out on this macOS host and fastbootd lacks `fastboot boot`, so there is no RAM-only test route.

Before a `boot_a` experiment, keep the original boot image and verified backups of `persist`, `nvdata`, `nvcfg`, `nvram`, `proinfo` and `sec1`, and obtain Android 16 stock firmware. Restoring the saved `boot_a` through fastbootd is the rollback while Android remains reachable. A consumed marker cannot reset a hang; a forced restart before consumption repeats the experiment.

The unbrick path is SP Flash Tool v6 with matching Android 16 stock firmware, using "Firmware Upgrade" or "Download Only". Android 13 firmware is blocked by anti-rollback. Never use "Format All + Download", which destroys calibration and IMEI, and never relock modified software. Review the recovery route with the phone present before flashing.

## Inputs Kept Locally

Vendor images and modules stay in `fw/`, phone observations and partition backups in `recon/`, and generated output in `out/`. Apple images are supplied by path and are not committed. [shim/soc.args](shim/soc.args) records the board facts and their sources.

```sh
python tools/extract-dt.py vendor_boot.img dtbo.img --out fw
python tools/check-facts.py
```

The checker reads `fw/jellystar.dtb`, `fw/dtbo.img` and, when present, `recon/live.dtb`; the packaged DT disagrees with the phone's framebuffer and panel, so the live reservation is authoritative. `tools/recon.sh` collects read-only Android observations, `tools/unpack-vendor-ramdisk.sh` and `tools/panel-init.py` recover vendor panel data, and `tools/touch-report.py REPORT.bin` decodes a saved 28-byte CHSC report.

## Credits & Licences

Original tools and Jelly Star work use the repository's [MIT licence](LICENSE). Apple's XNU and the local patches to it use APSL 2.0. HelioDarwin's tooling keeps its MIT licence in the pinned dependency and its XNU patches keep APSL provenance. The CHSC/I2C code implements protocol and register facts without importing GPL driver bodies. Apple, Unihertz and MediaTek binaries are supplied locally and not redistributed.

- [HelioDarwin](https://github.com/squeeeezy/HelioDarwin): XNU on the MT6789 Infinix Note 12 2023; SoC and driver reference.
- [KLiOS716](https://github.com/lib-fluff-so/KLiOS716) (`318f265a7e975cc12ef4bfe063ad029026e90105`): MT6789 port, boot and root reference; no code imported.
- [HakiOS MT6768](https://github.com/oosexgang/hakios-mt6768) (`4711c19068e5bb8b1ff6898e83add5392e40dd61`): Android-default MediaTek chainloader precedent; no code imported.
- [ios-sweet](https://github.com/dipa-studio/ios-sweet) and [ios-topaz](https://github.com/MakrSas/ios-topaz): upstream XNU-on-Android work.
- [Jelly Star LineageOS](https://github.com/osquera/lineageos_unihertz_jellystar): vendor-image and recovery references.
- [Volla MT6789 kernel](https://github.com/HelloVolla/android_kernel_volla_mt6789/tree/0b0e1435e568a4d2b5e9dceef0772bb1bc4786c5): CHSC5xxx protocol, `i2c-mt65xx.c` (DMA for reads beyond its 16-byte FIFO), MT6789 clocks, pinctrl, UFS and USB; GPL reference only.
- [MT6789 U-Boot](https://github.com/mnnoee/u-boot-mtk-g99/tree/4f238b0caf1430c888a83516dd93e16cdccccb9f): MUSB, USB PHY and clock references.
- [Ruby iOS bring-up](https://github.com/lky005/ruby-ios-bringup/tree/1aaa883755e546726b2f3a49a3ad099d77de4e62): MT6877/XNU 8796 CPU-copy display, EINT/HID and USB precedents.
- [MindOne MT6789 Linux forward-port](https://github.com/iasnezhkov/android_kernel_ikko_mindone/tree/d7e4ba6a8ade4e181b348f52bcc8c9801cb43f8c): USB, I2C, UFS and clock cross-check.
- [UniXNU Yunluo](https://github.com/woaphone/UniXNU-yunluo/tree/8df215c7a494e94392f6b38f02aa2f407db52553): MT6789 SMP, interrupt and UFS reference.
- [Linux AArch64 boot protocol](https://docs.kernel.org/arch/arm64/booting.html), [Linux 5.10 ramoops](https://github.com/torvalds/linux/blob/v5.10/fs/pstore/ram.c) and [AOSP boot headers](https://source.android.com/docs/core/architecture/bootloader/boot-image-header): format and handoff references; no source copied.
