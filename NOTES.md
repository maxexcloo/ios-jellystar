# Notes

Newest first. One entry per milestone, with the kernel and image hashes and what the panel actually showed.
Nothing on the phone yet; this file stays short until something runs.

## 2026-11-06 — device facts read, plan written

- Extracted `jellystar.dtb` (197,901 B, FDT 197,837 B) and `dtbo.img` (1 overlay entry) from the Lineage
  `20261101` release's `vendor_boot.img` (header v4, page 4096, vendor ramdisk 25,881,637 B, dtb_addr
  `0x47c80000`) and `dtbo.img`. Both stay in `fw/`, git-ignored.
- Ran the addresses against the working X676C port: **16 SoC-level items are identical** (GICD/GICR, timer,
  UFS, DSI0, DISP_MUTEX0, Mali, MFG_TOP_CFG, the `0x1000x` block, PWRAP, TOPRGU, keypad, CPU topology and
  page size). 9 constants differ. 4 drivers have no counterpart.
- `tools/check-facts.py` is green: every address in `devices/jellystar/soc.args` re-derives from the DT.
- Two findings that change the shape of the work:
  1. `/chosen/atag,videolfb-lcmname` = `nt36672e_fhdp_dsi_vdo_60hz_jdi_dphy_drv` — a 1080×2400 panel, with
     `vramSize` 0x01be0000 (~29 MiB) sized for 1080×2400 buffers. Impossible on a 480×854 phone, so the base
     DTB is a shared family tree. The overlay then adds **two** panels to `dsi0`: `zhunyi,st7701,vdo` and
     `truly,td4330,cmd`. The Lineage tree's `kernel/README.md` admits it does not know which is fitted.
  2. Touch is **Chipsea `chsc5xxx`** at i2c0 `0x2e` (vendor module `chsc5xxx_touch.ko`), not FocalTech like
     every other MT6789 port. IRQ GPIO 9, reset GPIO 152, 480×854, 10 contacts, 3 capacitive keys.
- Not yet done: anything on the phone. Next is step 0 in `docs/jellystar/port-plan.md` (read-only recon),
  whose outcome decides whether step 4 is one panel driver or two.
