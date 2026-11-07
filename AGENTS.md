# iOS Jelly Star

- Scope is Jelly Star/MT6789. README owns observed status; `shim/soc.args` owns board facts and source references. Verify facts against local firmware with `tools/check-facts.py`; packaged framebuffer/panel properties differ from the phone.
- Preserve the complete Android Image, generic ramdisk, unaffected header fields and LK FDT. Android is the default path; do not change inherited MMU/cache/exception-level configuration or touch MMIO on that path.
- Consume the diagnostic marker before display writes, stay inside the matching live framebuffer reservation and continue into Android. Do not rely on the trigger as a hang watchdog.
- Slot A is the only bootable chain and `fastboot boot` is unavailable. Review the recovery requirements in README before any boot-image experiment.
- Root preparation must invalidate MobileGestalt's hardware cache after advertised capabilities change; camera/flash advertisement requires functioning media services. Replace loaded signed executables by rename.
- Run `mise run check`; for loader changes also run `mise run build -- SAVED_BOOT_IMAGE`. Offline checks establish structure and host behaviour only.
