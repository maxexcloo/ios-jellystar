# Credits & Licences

Original tools and Jelly Star work use the repository's [MIT licence](LICENSE). Apple, Unihertz and MediaTek binaries are supplied locally and are not redistributed.

- [HelioDarwin](https://github.com/squeeeezy/HelioDarwin): XNU on the MT6789 Infinix Note 12 2023; SoC/driver reference.
- [KLiOS716](https://github.com/lib-fluff-so/KLiOS716): another MT6789 port and boot reference; its software renderer is not GPU-accelerated UI evidence.
- [HakiOS MT6768](https://github.com/oosexgang/hakios-mt6768): Android-default MediaTek chainloader precedent; different SoC, storage and boot-image version. No loader code is vendored here.
- [ios-sweet](https://github.com/dipa-studio/ios-sweet) and [ios-topaz](https://github.com/MakrSas/ios-topaz): upstream XNU-on-Android work. Topaz is Qualcomm SM6225, not MT6789.
- [Jelly Star LineageOS](https://github.com/osquera/lineageos_unihertz_jellystar): vendor-image/recovery references.
- [Linux AArch64 boot protocol](https://docs.kernel.org/arch/arm64/booting.html), [Linux 5.10 ramoops](https://github.com/torvalds/linux/blob/v5.10/fs/pstore/ram.c) and [AOSP boot headers](https://source.android.com/docs/core/architecture/bootloader/boot-image-header): format and handoff references; no source copied.

Apple's XNU uses APSL 2.0. Upstream projects retain their own licences; this repository currently contains no XNU patch series or imported kernel drivers.
