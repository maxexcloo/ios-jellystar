#!/bin/sh
# Everything that can be checked without a phone. Run from anywhere.
#
#   tools/check.sh
#
# Green here means: the DT reader works, the fact set still matches the DT on
# disk, and the status page matches device.conf. It says nothing about the
# phone, and nothing about whether any of this boots.
set -eu
cd "$(dirname "$0")/.."

fail=0

say() { printf '\n== %s\n' "$1"; }

say "python syntax"
for f in tools/*.py; do
	python3 -m py_compile "$f" && echo "ok   $f" || fail=1
done

say "fdt.py reads the extracted device tree"
if [ -f fw/jellystar.dtb ]; then
	python3 tools/fdt.py get fw/jellystar.dtb / compatible >/dev/null \
		&& echo "ok   fw/jellystar.dtb" || fail=1
	python3 tools/fdt.py nodes fw/dtbo.img >/dev/null \
		&& echo "ok   fw/dtbo.img" || fail=1
else
	echo "skip fw/ absent (vendor images are not in git: see README)"
fi

say "soc.args agrees with the device tree"
if [ -f fw/jellystar.dtb ]; then
	python3 tools/check-facts.py || fail=1
else
	echo "skip fw/ absent"
fi

say "the status page matches device.conf"
python3 -I tools/docs-gen.py jellystar --check || fail=1

say "the delta document is regenerated, not stale"
if [ -n "${HELIODARWIN:-}" ]; then
	python3 tools/diff-port.py --out /tmp/diff-vs-x676c.md >/dev/null \
		&& cmp -s /tmp/diff-vs-x676c.md docs/jellystar/diff-vs-x676c.md \
		&& echo "ok   docs/jellystar/diff-vs-x676c.md" \
		|| { echo "STALE: rerun tools/diff-port.py"; fail=1; }
else
	echo "skip HELIODARWIN not set (no reference checkout)"
fi

printf '\n'
[ "$fail" = 0 ] && echo "all checks passed" || echo "checks failed"
exit "$fail"
