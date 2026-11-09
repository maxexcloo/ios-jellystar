# iOS Jellystar

- Scope is Jelly Star / jellystar / MT6789. README owns observed status and recovery; `shim/soc.args` owns board facts and their sources; `xnu/sources.toml` owns pinned upstreams; `xnu/patches/` and `xnu/jellystar/` own kernel changes.
- Verify board facts against local firmware with `python tools/check-facts.py`; the packaged framebuffer/panel properties differ from the phone, and the live reservation is authoritative.
- Preserve the complete Android image, generic ramdisk, unaffected header fields and LK FDT. Android is the default path: do not change inherited MMU/cache/exception-level configuration or touch MMIO on it.
- Consume a marker before display writes or XNU entry, stay inside the matching live framebuffer reservation and continue into Android when not entering XNU. The one-shot trigger is not a hang watchdog.
- Slot A is the only bootable chain and `fastboot boot` is unavailable. Review README recovery with the phone present before any boot-image experiment.
- Root preparation must invalidate MobileGestalt's hardware cache after advertised capabilities change; keep camera/flash unadvertised until media services work. Replace loaded signed executables by rename.
- Run `mise run check`; after loader changes also run `mise run build -- SAVED_BOOT_IMAGE`. Offline checks establish structure and host behaviour only.
