"""Prepare a standalone D22AP HFS+ root on macOS, without choosing a partition.

Use --check-inputs to resolve a locally supplied BuildManifest without mounting
anything. A full build needs root to preserve iOS numeric ownership. Source
images are attached read-only; all writable mounts belong to the new output.
"""

import argparse
import os
import plistlib
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("OS", "Cryptex1,SystemOS", "Cryptex1,AppOS")


def inputs(manifest):
    data = plistlib.loads(manifest.read_bytes())
    if (data["ProductVersion"], data["ProductBuildVersion"]) != ("16.7.16", "20H392"):
        raise ValueError("The pinned root tweaks require iOS 16.7.16 / 20H392")
    identity = next(
        item
        for item in data["BuildIdentities"]
        if item["Info"]["DeviceClass"] == "d22ap"
        and item["Info"]["RestoreBehavior"] == "Erase"
    )
    paths = [
        manifest.parent / identity["Manifest"][key]["Info"]["Path"]
        for key in COMPONENTS
    ]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    return paths


def invalidate_capabilities(root):
    # Old camera/flash answers can block SpringBoard on unavailable media XPC.
    caches = root / "private/var/containers/Shared/SystemGroup"
    count = 0
    for path in caches.glob("*/Library/Caches/com.apple.MobileGestalt.plist"):
        path.unlink()
        count += 1
    return count


def cryptex_links(root):
    cache = "System/Library/Caches/com.apple.dyld"
    destination = root / cache
    destination.mkdir(parents=True, exist_ok=True)
    for path in (root / "private/preboot/Cryptexes/OS" / cache).iterdir():
        target = destination / path.name
        if os.path.lexists(target):
            target.unlink()
        os.link(path, target)
    for name in ("OS", "App"):
        source = root / "private/preboot/Cryptexes" / name
        for directory, directories, files in os.walk(source):
            files += [
                name for name in directories if (Path(directory) / name).is_symlink()
            ]
            for name in files:
                src = Path(directory) / name
                relative = src.relative_to(source)
                if relative.is_relative_to(cache):
                    continue
                dst = root / relative
                if os.path.lexists(dst):
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.is_symlink():
                    dst.symlink_to(os.readlink(src))
                    os.lchown(dst, src.lstat().st_uid, src.lstat().st_gid)
                else:
                    os.link(src, dst)


def finish_root(root, source):
    for name, mode in (
        ("diagnostics", 0o751),
        ("uuidtext", 0o755),
        ("diagnostics/timesync", 0o755),
    ):
        directory = root / "private/var/db" / name
        directory.mkdir(parents=True, exist_ok=True)
        os.chown(directory, 272, 272)
        directory.chmod(mode)
        marker = directory / ".migrated"
        marker.touch()
        os.chown(marker, 272, 272)
        marker.chmod(0o644)
    keybags = root / "private/var/keybags"
    keybags.mkdir(parents=True, exist_ok=True)
    os.chown(keybags, 0, 0)
    keybags.chmod(0o700)
    bag = keybags / "systembag.kb"
    bag.write_bytes(plistlib.dumps({"KeyBagKeys": b"SWEET"}))
    os.chown(bag, 0, 0)
    bag.chmod(0o600)
    subprocess.run(
        [sys.executable, "-B", str(source / "tools/sweet-root-tweaks.py"), str(root)],
        check=True,
        capture_output=True,
    )
    invalidate_capabilities(root)
    for relative, uid in (
        ("sbin/launchd", 0),
        ("private/var/keybags/systembag.kb", 0),
        ("private/var/db/diagnostics", 272),
    ):
        if (root / relative).stat().st_uid != uid:
            raise RuntimeError(f"Numeric ownership did not survive: {relative}")


def run(*args):
    return subprocess.check_output([str(arg) for arg in args], stderr=subprocess.PIPE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--check-inputs", action="store_true")
    parser.add_argument("--source", type=Path, default=ROOT / "out/sources/HelioDarwin")
    parser.add_argument("--out", type=Path, default=ROOT / "out/xnu/iosroot.img")
    parser.add_argument("--gib", type=int, default=16)
    args = parser.parse_args()
    images = inputs(args.manifest.resolve())
    print(
        "D22AP iOS 16.7.16 / 20H392 inputs: "
        + ", ".join(
            f"{name}={path.stat().st_size} bytes"
            for name, path in zip(COMPONENTS, images, strict=True)
        )
    )
    if args.check_inputs:
        return
    if sys.platform != "darwin" or os.geteuid() != 0:
        parser.error(
            "Run the full macOS image build as root to preserve numeric owners"
        )
    source = args.source.resolve()
    pin = tomllib.loads((ROOT / "xnu/sources.toml").read_text())["helio"]
    if run("git", "-C", source, "rev-parse", "HEAD").decode().strip() != pin["commit"]:
        parser.error(f"HelioDarwin must be checked out at {pin['commit']}")
    run("git", "-C", source, "diff", "--exit-code", "HEAD", "--", "tools")
    args.out = args.out.resolve()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("xb") as image:
        args.out.chmod(0o600)
        image.truncate(args.gib * 1024**3)
    devices = []
    work = Path(tempfile.mkdtemp(prefix="root-build-", dir=args.out.parent))

    def attach(path, name, readonly=False, nomount=False):
        flags = (
            ["-nomount"] if nomount else ["-mountpoint", work / name, "-owners", "on"]
        )
        if not nomount:
            (work / name).mkdir()
        if readonly:
            flags += ["-readonly"]
        else:
            flags += ["-imagekey", "diskimage-class=CRawDiskImage"]
        data = plistlib.loads(
            run(
                "hdiutil",
                "attach",
                "-plist",
                "-noautoopen",
                "-nobrowse",
                *flags,
                path,
            )
        )
        device = next(
            item["dev-entry"] for item in data["system-entities"] if "dev-entry" in item
        )
        devices.append(device)
        return device

    try:
        for name, path in zip(("OS", "SystemOS", "AppOS"), images, strict=True):
            attach(path, name, readonly=True)
        device = attach(args.out, "root", nomount=True)
        run("newfs_hfs", "-s", "-J", "-v", "JellyStarRoot", device)
        mount = work / "root"
        mount.mkdir()
        run(
            "diskutil",
            "mount",
            "-mountOptions",
            "owners",
            "-mountPoint",
            mount,
            device,
        )
        for name, destination in (
            ("OS", mount),
            ("SystemOS", mount / "private/preboot/Cryptexes/OS"),
            ("AppOS", mount / "private/preboot/Cryptexes/App"),
        ):
            destination.mkdir(parents=True, exist_ok=True)
            run(
                "rsync",
                "-aH",
                "--numeric-ids",
                str(work / name) + "/",
                str(destination) + "/",
            )
        cryptex_links(mount)
        finish_root(mount, source)
        run("diskutil", "unmount", device)
        run("diskutil", "verifyVolume", device)
    finally:
        failed = []
        for device in reversed(devices):
            try:
                run("hdiutil", "detach", device)
            except subprocess.CalledProcessError:
                failed.append(device)
        # Never recurse into mount points, including after a failed detach.
        for directory in work.iterdir():
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            work.rmdir()
        except OSError:
            pass
        if failed:
            raise RuntimeError(f"Host image mounts remain attached under {work}")
    # The image may have been built under sudo; let the calling user retain it.
    if "SUDO_UID" in os.environ:
        os.chown(args.out, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))
    args.out.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(
        f"Verified standalone HFS+ root: {args.out}; no Jelly Star partition selected"
    )


if __name__ == "__main__":
    main()
