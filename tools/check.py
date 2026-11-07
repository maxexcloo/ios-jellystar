"""Run loader tests and check available vendor inputs without a phone."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
subprocess.run(
    [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
    cwd=ROOT,
    check=True,
)
if (ROOT / "fw/jellystar.dtb").is_file() and (ROOT / "fw/dtbo.img").is_file():
    subprocess.run([sys.executable, "-B", "tools/check-facts.py"], cwd=ROOT, check=True)
else:
    print("Vendor DT checks not run: supply fw/jellystar.dtb and fw/dtbo.img locally")
