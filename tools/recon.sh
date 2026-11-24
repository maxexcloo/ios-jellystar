#!/bin/sh
# Read-only reconnaissance on a Jelly Star running Android (or a GSI).
#
#   tools/recon.sh [SERIAL] [OUTDIR]      # default OUTDIR: recon/
#
# Needs `adb root`: /proc/device-tree is EACCES for the shell user. Nothing here
# writes to the phone. Output goes to OUTDIR, which is git-ignored because the
# live device tree carries the unit's serial.
#
# What this answers, and why each one matters:
#   * which panel driver is *bound* (not what /chosen claims -- they disagree here)
#   * the touch controller's i2c address and driver (no XNU driver exists for it)
#   * the real DRAM shape and the reserved-memory carve-outs (framebuffer, pstore)
#   * the boot slot and lock state, before anything is flashed
set -eu
cd "$(dirname "$0")/.."

SERIAL="${1:-}"
OUT="${2:-recon}"
ADB="adb"
[ -n "$SERIAL" ] && ADB="adb -s $SERIAL"

mkdir -p "$OUT"

read_text() {
	data=$($ADB shell "$1") || return
	printf '%s\n' "$data" | tr -d '\r'
}
cap() {
	data=$(read_text "$2")
	printf '%s' "$data" | awk -v pattern="${3:-}" 'tolower($0) ~ pattern' > "$OUT/$1.txt"
	echo "  $OUT/$1.txt"
}

echo "== identity"
UID_=$(read_text id)
case "$UID_" in
*uid=0*) echo "  root ok" ;;
*) echo "  NOT root: run 'adb root' first (/proc/device-tree needs it)"; exit 1 ;;
esac

for p in ro.board.platform ro.product.device ro.product.model ro.build.version.release \
         ro.build.fingerprint ro.boot.hardware ro.boot.slot_suffix \
         ro.boot.verifiedbootstate ro.boot.flash.locked; do
	value=$(read_text "getprop $p")
	printf '%-28s %s\n' "$p" "$value"
done

echo
echo "== panel (bound driver beats /chosen's name)"
lcm=$(read_text 'test ! -r /proc/device-tree/chosen/atag,videolfb-lcmname || tr -d "\000" < /proc/device-tree/chosen/atag,videolfb-lcmname')
modes=$(read_text 'test ! -r /sys/class/drm/card0-DSI-1/modes || cat /sys/class/drm/card0-DSI-1/modes')
size=$(read_text 'wm size')
density=$(read_text 'wm density')
echo "  /chosen lcmname: $lcm"
echo "  DRM mode:        $(printf '%s' "$modes" | tr '\n' ' ')"
echo "  wm size/density: $(printf '%s' "$size" | tr -d '\n') / $(printf '%s' "$density" | tr -d '\n')"
echo "  panel modules:"
cap panel-lsmod lsmod 'panel|mtk_panel_ext'
sed 's/^/    /' "$OUT/panel-lsmod.txt"

echo
echo "== touch"
touch=$(read_text 'test ! -r /sys/bus/i2c/devices/0-002e/name || cat /sys/bus/i2c/devices/0-002e/name')
echo "  0-002e name: $touch"
cap input-devices 'cat /proc/bus/input/devices'
cap touch-lsmod lsmod 'chsc|touch'

echo
echo "== memory"
memory=$(read_text 'od -An -tx1 -v /proc/device-tree/memory/reg')
total=$(read_text 'grep MemTotal /proc/meminfo')
echo "  /memory/reg: $(printf '%s' "$memory" | tr -d ' \n')"
echo "  MemTotal:    $(printf '%s' "$total" | tr -s ' ')"
# These single-quoted programs run on the phone, not in the host shell.
# shellcheck disable=SC2016
cap reserved-memory 'for d in /proc/device-tree/reserved-memory/*/; do printf "%-40s " "$(basename "$d")"; od -An -tx1 -v "$d/reg" 2>/dev/null | tr -d "\n "; echo; done'
# shellcheck disable=SC2016
cap chosen 'for f in /proc/device-tree/chosen/*; do printf "%-32s " "$(basename "$f")"; od -An -tx1 -v "$f" 2>/dev/null | tr -d "\n "; echo; done'

echo
echo "== cpus"
# shellcheck disable=SC2016
cpus=$(read_text 'for c in /sys/devices/system/cpu/cpu[0-9]; do printf "%-5s core_id=%s capacity=%s\n" $(basename $c) $(cat $c/topology/core_id) $(cat $c/cpu_capacity); done')
printf '%s\n' "$cpus" | sed 's/^/  /'

echo
echo "== storage (partition table, read-only)"
cap partitions 'ls -l /dev/block/by-name/ 2>/dev/null'
cap mounts mount 'userdata|super|metadata'

live=$(mktemp "$OUT/.live.dtb.XXXXXX")
trap 'rm -f "$live"' EXIT
$ADB shell -T 'cat /sys/firmware/fdt' > "$live"
mv "$live" "$OUT/live.dtb"

echo
echo "done. Review $OUT/ before committing anything: the live DT has the serial."
[ "$OUT" != recon ] || echo "next: mise exec -- python tools/check-facts.py"
