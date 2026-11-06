# ios-jellystar

iOS 16 (XNU `xnu-8796`) on the **Unihertz Jelly Star** — MediaTek MT6789 / Helio G99, 8 GiB RAM,
3.0" 480×854 LCD, Mali-G57 MC2.

**Status: nothing has run on a phone.** This is the research and planning stage: the hardware facts are
read out of the phone's own device tree, the delta against the one existing MT6789 port is written down,
and neither has been flashed.

## Why it is worth trying

The Jelly Star's SoC is the same MT6789 as the Infinix Note 12 2023, which
[`squeeeezy/HelioDarwin`](https://github.com/squeeeezy/HelioDarwin) already boots iOS 16 on — GICv3,
generic timer, MTK UFS, the DSI/display controller, PWRAP to the MT6366 PMIC, TOPRGU and the Mali-G57
are at identical addresses. `tools/diff-port.py` counts the delta at **16 unchanged, 9 constants and
4 new drivers**. The two real unknowns are the *panel* (the DT names a 1080×2400 sibling and the overlay
offers two candidates) and *touch* (a Chipsea `chsc5xxx`, which no existing port drives).

Full reasoning: [`docs/jellystar/port-plan.md`](docs/jellystar/port-plan.md).
The itemised delta: [`docs/jellystar/diff-vs-x676c.md`](docs/jellystar/diff-vs-x676c.md).
Status, and the only status that counts: [`docs/devices/jellystar.md`](docs/devices/jellystar.md).

## Device facts, and how they are trusted

Every address in [`devices/jellystar/soc.args`](devices/jellystar/soc.args) names the device-tree node it
came from. `tools/check-facts.py` re-reads the DT and fails if the file drifts:

```sh
# get the vendor images (LineageOS 20261101 release, or Unihertz's Android 16 firmware)
tools/extract-dt.py vendor_boot.img dtbo.img --out fw
python3 tools/check-facts.py
```

```
soc_gicd               ok      0xc000000
soc_ufs                ok      0x11270000
soc_touch_addr         ok      0x2e
soc_cpu_mpidr          ok      8 cores (6 A55 + 2 A76)
...
all checkable facts match the device tree (6 skipped: not in the DT)
```

The skipped six are the facts the device tree does not contain (480×854 geometry, which comes from the
Android side) or that contradict it (`/chosen` names a panel that cannot be fitted). They are printed with
the reason rather than counted as verified.

## What is in the box

| Path | What |
|---|---|
| `devices/jellystar/soc.args` | the SoC map, each line citing its DT node |
| `devices/jellystar/device.conf` | subsystem status — all `missing` |
| `docs/jellystar/port-plan.md` | the plan, the risks, the boot/recovery rules for this phone |
| `docs/jellystar/diff-vs-x676c.md` | generated delta against HelioDarwin, with `file:line` pointers |
| `tools/` | DT reader/extractor, fact checker, delta generator, status page generator |
| `fw/` | local only: `jellystar.dtb`, `dtbo.img` (git-ignored vendor binaries) |
| `recon/` | local only: anything read off the phone (git-ignored; the live DT has the serial) |

## Next step

One `adb` command decides the project's shape — which panel is actually fitted:

```sh
adb shell cat /proc/device-tree/chosen/atag,videolfb-lcmname
adb shell dmesg | grep -iE "lcm|panel|chsc|touch"
```

See "step 0" in the port plan for the rest of the read-only recon, and "step 2" for the first thing that
touches the phone: a shim on `boot_b` that draws text and returns to Android.

## Credits and licences

This repository contains original work (the tools, the fact set, the plan) under the MIT Licence.

It builds on, and reads from, other people's work that is **not** copied here:

- [squeeeezy/HelioDarwin](https://github.com/squeeeezy/HelioDarwin) — the MT6789 XNU port this plan
  targets as a base (independent research project).
- [lib-fluff-so/KLiOS716](https://github.com/lib-fluff-so/KLiOS716) and `KLiOS716-shim` — the TECNO KL7 MT6789
  port, and the boot/recovery discipline quoted in the plan.
- [MakrSas/ios-topaz](https://github.com/MakrSas/ios-topaz) and
  [dipa-studio/ios-sweet](https://github.com/dipa-studio/ios-sweet) — the upstream XNU-on-Android work.
- [osquera/lineageos_unihertz_jellystar](https://github.com/osquera/lineageos_unihertz_jellystar) — the
  LineageOS port whose release images the device tree is extracted from, and whose notes document this
  phone's boot chain.
- [UniXNU/UniXNU](https://github.com/UniXNU/UniXNU) — catalogue of ports consulted for feasibility.
- Apple's XNU is under the Apple Public Source License 2.0.

No Apple, Unihertz or MediaTek binary is redistributed here. Apple's iOS images, Unihertz's firmware and
the extracted device trees must be supplied by whoever runs this.
