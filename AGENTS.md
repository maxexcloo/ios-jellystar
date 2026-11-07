# iOS Jelly Star

- Scope is the Jelly Star/MT6789. `devices/jellystar/device.conf` is the status record; nothing is working until observed on this phone. Hardware facts and sources belong in `soc.args`; run `tools/check-facts.py` against local firmware after changing them.
- Slot B has no boot chain; `fastboot boot` is unavailable. Slot A is the only Android boot path. The chainloader must enter the saved Android kernel by default, preserving its complete Image, ramdisk and LK FDT. Its fallback has not been tested.
- Do not flash `boot_a` until Android 16 recovery firmware, the original boot image and verified calibration backups are available. Never relock, format all in SP Flash Tool or provision slot B casually. Confirm every data-erasing action immediately before it.
- The diagnostic trigger is one-shot: consume it before touching display hardware, then continue into Android. Runtime writes must stay inside the live framebuffer reservation. Keep the Android path free of MMIO and changes to MMU, cache or exception-level configuration.
- The packaged DT's panel name/framebuffer is misleading. Use live DT reservations and identified bound drivers; a Chipsea firmware-update blob does not establish volatile firmware.
- Run `mise run check`; build with `mise run build -- SAVED_BOOT_IMAGE`. Offline checks establish image structure and host behaviour only. Firmware, phone dumps/logs, Apple material and generated images remain outside git and tool output.
- Future root preparation must invalidate MobileGestalt’s hardware cache when advertised capabilities change; camera/flash advertisements require working media services. Replace loaded signed executables by rename.
