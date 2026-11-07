# iOS Jelly Star

Experimental iOS 16 / XNU bring-up for the Unihertz Jelly Star (MT6789 / Helio G99). **No custom code has executed on this phone.** [device.conf](devices/jellystar/device.conf) records subsystem status; [soc.args](devices/jellystar/soc.args) owns the hardware facts and their sources.

The closest base is [HelioDarwin](https://github.com/squeeeezy/HelioDarwin), whose same-SoC phone reaches iOS userspace with UFS storage and display. Its GPU job completion does not establish correctly accelerated UI. Jelly needs its own ST7701S video-mode panel and Chipsea `chsc5xxx` touch drivers. Firmware embedded in the touch module does not prove it must be uploaded on every reset. See [CREDITS.md](CREDITS.md) for references and licences.

## Build & Check

Host tools use Python's standard library and a C compiler. The chainloader build also needs LLVM (`clang`, `ld.lld`, `llvm-objcopy`, `llvm-nm`, `llvm-readelf`). Set `CC`, `LD`, `OBJCOPY`, `NM` and `READELF` if those tools are not on PATH; the builder also recognises Homebrew's keg-only LLVM directory.

```sh
mise run check
mise run build -- recon/backup/boot_a.img
```

The build produces `out/chainboot/chainboot.img`. It embeds the complete Android Image at a 2 MiB boundary, preserving its text offset, all appended data, the boot header's other fields and the generic ramdisk. The modified kernel invalidates the old GKI signature and AVB footer, which are omitted. `vendor_boot`, DTBO and bootloader partitions are not involved in this offline build.

The default loader simply enters Android. A separate diagnostic build enables a one-shot `JELLYSTAR:DIAGNOSTIC` marker in the ramoops pmsg ring:

```sh
mise run build -- recon/backup/boot_a.img --out out/diagnostic --diagnostic
```

When triggered, it consumes the marker before drawing a green frame, waits five seconds and continues into Android. It only draws when the live DT's framebuffer address matches its reservation and has room for the panel. The pmsg location is derived from the saved Linux 5.10 ramoops layout, including its default ftrace page; trigger survival and the persistent header still need hardware validation. No XNU payload is included yet.

Checks cover boot-image preservation, deterministic packing, trigger consumption across ring wrap, rejection of unrecorded triggers and live framebuffer selection. Local builds have round-tripped the saved Android kernel and ramdisk. **These checks do not prove LK loading or Android fallback.**

## Hardware Boundary

The attempted `boot_b` shim never executed: every slot-B boot-chain partition was zero, so the preloader failed and eventually returned to A. Flashing `boot_b` alone cannot fix that. LK's fastboot transfers time out on this macOS host; Android fastbootd works but cannot perform `fastboot boot`. No usable RAM-only boot route has been demonstrated.

The next device experiment is the Android-only chainloader, followed by the one-shot diagnostic after Android fallback is observed. The [HakiOS MT6768 loader](https://github.com/oosexgang/hakios-mt6768) is the precedent for chaining Android; its addresses, eMMC driver and boot-v2 packer do not apply directly here.

Before any `boot_a` experiment, have the original boot image, verified calibration backups and Android 16 stock recovery firmware available. Slot A is the only bootable slot. Do not relock the bootloader or use SP Flash Tool's “Format All + Download”; Android 13 rollback is blocked. No flashing command is supplied until the experiment and recovery path are reviewed with the phone present.

After loader execution is proved, the remaining sequence is the HelioDarwin XNU/ADT port, storage/root layout, panel scanout and touch. Networking, GPU UI, audio, cameras and other peripherals need separate driver work and hardware evidence. The small screen also needs actual UIKit layout testing.

## Hardware Inputs

Vendor images, device dumps and Apple's material stay local. To extract and check the supplied vendor DTs:

```sh
python3 tools/extract-dt.py vendor_boot.img dtbo.img --out fw
python3 tools/check-facts.py
```

`fw/jellystar.dtb` and `fw/dtbo.img` come from the matching vendor images. `recon/live.dtb` is the captured DT that LK actually passed; it contains private device identifiers and is never committed. The packaged DT's panel name/framebuffer differs from this phone, so the checker reports those discrepancies rather than treating the packaged values as authoritative.

`tools/recon.sh` collects read-only Android observations when explicitly requested. `tools/unpack-vendor-ramdisk.sh` extracts local vendor modules, and `tools/panel-init.py` decodes the ST7701S init objects and timings. These are research inputs, not working XNU drivers.
