# Unihertz Jelly Star (jellystar): status

Made by `tools/docs-gen.py jellystar` from [devices/jellystar/device.conf](../../devices/jellystar/device.conf); edit that file, not this page.

| | |
|---|---|
| title | Unihertz Jelly Star |
| vendor | Unihertz |
| soc | mt6789 (Helio G99, 6x A55 + 2x A76, Mali-G57 MC2) |
| ios | iOS 16.7.16 (iPhone X D22AP userland, target, not yet attempted) |
| base | squeeeeezy/HelioDarwin (Infinix Note 12 2023, same MT6789) -- nothing applied to this phone |
| boot | plan: boot_b (virtual A/B, Android stays on boot_a); no fastboot boot on MTK LK |
| facts | devices/jellystar/soc.args, checked by tools/check-facts.py against the DT |
| dt | fw/jellystar.dtb + fw/dtbo.img from tools/extract-dt.py (Lineage 20261101) |
| plan | docs/jellystar/port-plan.md, docs/jellystar/diff-vs-x676c.md |

## Subsystems

0 works, 0 partial, 17 missing (of 17).

| Subsystem | State | Notes |
|---|---|---|
| boot | missing | nothing built or flashed; image layout not chosen |
| display | missing | panel unresolved: overlay offers ST7701S (vdo) *and* TD4330 (cmd), 480x854 |
| touch | missing | Chipsea chsc5xxx on i2c0 0x2e -- no driver exists in any port |
| gpu | missing | Mali-G57 MC2 at 0x13000000, same part as the working X676C port |
| cpu | missing | 6x A55 published, 2x A76 excluded (same choice as X676C) |
| storage | missing | MTK UFS at 0x11270000, same host as X676C; iosroot carve undesigned |
| buttons | missing | MT6366 keys on pwrap (power 116, func2 250), keypad 0x10010000 (volume 114/115, red key scan 249) |
| backlight | missing | disp_pwm0 0x1100e000 behind whichever panel is fitted |
| battery | missing | MT6366 fuel gauge not driven |
| usb | missing | MT6789 MUSB 0x11200000 + T-PHY, Qualcomm DWC3 driver does not apply |
| wifi | missing | MediaTek consys@18002000 (Wi-Fi/BT combo behind the connectivity DSP) -- no MTK Wi-Fi in any XNU port |
| bluetooth | missing | same chip as Wi-Fi |
| cellular | missing | MD modem, not started |
| audio | missing | not started |
| camera | missing | not started |
| sensors | missing | not started |
| nfc | missing | TMS NFC at i2c3, not started |
