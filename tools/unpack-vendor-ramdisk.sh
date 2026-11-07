#!/bin/sh
# Unpack the vendor ramdisk out of the phone's vendor_boot, where the panel and
# touch drivers actually live.
#
#   tools/unpack-vendor-ramdisk.sh [SERIAL] [SLOT] [OUTDIR]
#
# Defaults: SERIAL = $ANDROID_SERIAL or the only attached device, SLOT = a,
# OUTDIR = recon/vendorboot (git-ignored: it is vendor binary material).
#
# Why this exists: /vendor/lib/modules does NOT contain panel-ST7701S_Z30043.ko
# or chsc5xxx_touch.ko on this phone. They ship in vendor_boot's vendor ramdisk
# (LZ4 legacy frames wrapping a newc cpio). `lsmod` shows them loaded, so their
# absence from /vendor is a red herring that costs an hour if you trust ls only.
#
# Reads the phone; writes only under OUTDIR. Nothing is flashed.
set -eu
cd "$(dirname "$0")/.."

SERIAL="${1:-${ANDROID_SERIAL:-}}"
SLOT="${2:-a}"
OUT="${3:-recon/vendorboot}"
ADB="adb"
[ -n "$SERIAL" ] && ADB="adb -s $SERIAL"

mkdir -p "$OUT"

echo "== dumping vendor_boot_$SLOT from the phone (64 MiB, read-only)"
$ADB exec-out "cat /dev/block/by-name/vendor_boot_$SLOT" > "$OUT/vendor_boot.img"

echo "== splitting the v4 header: ramdisk and DTB"
python3 tools/unpack-vendor-boot.py "$OUT/vendor_boot.img" --out "$OUT"

RD="$OUT/vendor_ramdisk.bin"
if [ ! -f "$RD" ]; then
	echo "no vendor_ramdisk.bin produced (header may be v3, or the slot is empty)" >&2
	exit 1
fi

echo "== unpacking the LZ4-legacy cpio"
rm -rf "$OUT/ramdisk"
mkdir -p "$OUT/ramdisk"
if ! lz4 -l -d -f "$RD" "$OUT/vendor_ramdisk.cpio" 2>/dev/null; then
	echo "lz4 legacy decode failed; first bytes are:" >&2
	od -An -tx1 -N8 "$RD" >&2
	exit 1
fi
(cd "$OUT/ramdisk" && cpio -idm --quiet < "../vendor_ramdisk.cpio" 2>/dev/null || true)

echo
echo "== the modules the plan is blocked on"
for m in panel-ST7701S_Z30043.ko chsc5xxx_touch.ko mtk_panel_ext.ko; do
	p="$OUT/ramdisk/lib/modules/$m"
	if [ -f "$p" ]; then
		printf '  %-32s %8s bytes\n' "$m" "$(wc -c < "$p" | tr -d ' ')"
	else
		printf '  %-32s MISSING\n' "$m"
	fi
done

echo
echo "next: python3 tools/panel-init.py $OUT/ramdisk/lib/modules/panel-ST7701S_Z30043.ko"
echo "      (decodes the DCS init sequence and the 480x854 timing table)"
