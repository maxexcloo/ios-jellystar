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

sh_() { $ADB shell "$1" 2>&1 | tr -d '\r'; }
cap() { sh_ "$2" > "$OUT/$1.txt"; echo "  $OUT/$1.txt"; }

echo "== identity"
UID_=$($ADB shell id 2>/dev/null | tr -d '\r')
case "$UID_" in
*uid=0*) echo "  root ok" ;;
*) echo "  NOT root: run 'adb root' first (/proc/device-tree needs it)"; exit 1 ;;
esac

i=0
for p in ro.board.platform ro.product.device ro.product.model ro.build.version.release \
         ro.build.fingerprint ro.boot.hardware ro.boot.slot_suffix \
         ro.boot.verifiedbootstate ro.boot.flash.locked; do
	printf '%-28s %s\n' "$p" "$($ADB shell getprop $p 2>/dev/null | tr -d '\r')"
	i=$((i+1))
done

echo
echo "== panel (bound driver beats /chosen's name)"
echo "  /chosen lcmname: $(sh_ 'cat /proc/device-tree/chosen/atag,videolfb-lcmname' | tr -d '\0')"
echo "  DRM mode:        $(sh_ 'cat /sys/class/drm/card0-DSI-1/modes 2>/dev/null' | tr '\n' ' ')"
echo "  wm size/density: $(sh_ 'wm size' | tr -d '\n') / $(sh_ 'wm density' | tr -d '\n')"
echo "  panel modules:"; sh_ 'lsmod | grep -iE "^panel_|panel-" | sed "s/^/    /"'
cap panel-lsmod 'lsmod | grep -iE "panel|mtk_panel_ext"'

echo
echo "== touch"
echo "  0-002e name: $(sh_ 'cat /sys/bus/i2c/devices/0-002e/name 2>/dev/null')"
cap input-devices 'cat /proc/bus/input/devices'
cap touch-lsmod 'lsmod | grep -iE "chsc|touch"'

echo
echo "== memory"
echo "  /memory/reg: $(sh_ 'od -An -tx1 -v /proc/device-tree/memory/reg' | tr -d ' \n')"
echo "  MemTotal:    $(sh_ 'grep MemTotal /proc/meminfo' | tr -s ' ')"
# These single-quoted programs run on the phone, not in the host shell.
# shellcheck disable=SC2016
cap reserved-memory 'for d in /proc/device-tree/reserved-memory/*/; do printf "%-40s " "$(basename "$d")"; od -An -tx1 -v "$d/reg" 2>/dev/null | tr -d "\n "; echo; done'
# shellcheck disable=SC2016
cap chosen 'for f in /proc/device-tree/chosen/*; do printf "%-32s " "$(basename "$f")"; od -An -tx1 -v "$f" 2>/dev/null | tr -d "\n "; echo; done'

echo
echo "== cpus"
# shellcheck disable=SC2016
sh_ 'for c in /sys/devices/system/cpu/cpu[0-9]; do printf "%-5s core_id=%s capacity=%s\n" $(basename $c) $(cat $c/topology/core_id) $(cat $c/cpu_capacity); done' |
	sed 's/^/  /'

echo
echo "== storage (partition table, read-only)"
cap partitions 'ls -l /dev/block/by-name/ 2>/dev/null'
cap mounts 'mount | grep -iE "userdata|super|metadata"'

echo
echo "done. Review $OUT/ before committing anything: the live DT has the serial."
echo "next: python3 tools/check-facts.py   (then fill any PHONE/MISSING rows in shim/soc.args)"
