#!/usr/bin/env python3
"""Check host tooling and available local hardware inputs without a phone."""
import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
paths = subprocess.check_output(
    ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
).decode().split("\0")
for name in sorted(set(paths)):
    path = ROOT / name
    if not path.is_file():
        continue
    if path.suffix == ".py":
        ast.parse(path.read_text(), filename=name)
    elif path.suffix == ".sh":
        subprocess.run(["bash", "-n", str(path)], check=True)
subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT, check=True)
if (ROOT / "fw/jellystar.dtb").is_file() and (ROOT / "fw/dtbo.img").is_file():
    subprocess.run([sys.executable, "-B", "tools/check-facts.py"], cwd=ROOT, check=True)
else:
    print("Vendor DT checks not run: supply fw/jellystar.dtb and fw/dtbo.img locally")
subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
print("Host checks passed; no on-device result is established")
