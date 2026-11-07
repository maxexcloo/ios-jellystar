import importlib.util
import os
import plistlib
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "build_root", ROOT / "tools/build-root.py"
)
root_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(root_tools)


class RootPreparationTests(unittest.TestCase):
    def test_manifest_resolves_d22ap_erase_cryptexes(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            images = [directory / name for name in ("os.dmg", "system.dmg", "app.dmg")]
            for image in images:
                image.touch()
            identity = {
                "Info": {"DeviceClass": "d22ap", "RestoreBehavior": "Erase"},
                "Manifest": {
                    key: {"Info": {"Path": image.name}}
                    for key, image in zip(root_tools.COMPONENTS, images, strict=True)
                },
            }
            manifest = directory / "BuildManifest.plist"
            data = {
                "ProductVersion": "16.7.16",
                "ProductBuildVersion": "20H392",
                "BuildIdentities": [
                    {"Info": {"DeviceClass": "d221ap", "RestoreBehavior": "Erase"}},
                    identity,
                ],
            }
            manifest.write_bytes(plistlib.dumps(data))
            self.assertEqual(root_tools.inputs(manifest), images)
            images[-1].unlink()
            with self.assertRaises(FileNotFoundError):
                root_tools.inputs(manifest)
            data["ProductBuildVersion"] = "different-build"
            manifest.write_bytes(plistlib.dumps(data))
            with self.assertRaisesRegex(ValueError, "20H392"):
                root_tools.inputs(manifest)

    def test_cryptex_links_preserve_existing_files_and_symlink_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "private/preboot/Cryptexes/OS"
            app = root / "private/preboot/Cryptexes/App"
            app.mkdir(parents=True)
            cache = source / "System/Library/Caches/com.apple.dyld/cache"
            library = source / "System/Library/Foo.framework/Info.plist"
            existing = source / "usr/lib/existing"
            for path in (cache, library, existing):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"cryptex")
            alias = source / "System/Library/Alias.framework"
            alias.symlink_to("Foo.framework", target_is_directory=True)
            (root / "usr/lib").mkdir(parents=True)
            (root / "usr/lib/existing").write_bytes(b"original")
            old_cache = root / cache.relative_to(source)
            old_cache.parent.mkdir(parents=True)
            old_cache.write_bytes(b"old cache")
            root_tools.cryptex_links(root)
            for path in (cache, library):
                destination = root / path.relative_to(source)
                self.assertEqual(destination.stat().st_ino, path.stat().st_ino)
            self.assertEqual((root / "usr/lib/existing").read_bytes(), b"original")
            self.assertEqual(
                os.readlink(root / "System/Library/Alias.framework"), "Foo.framework"
            )

    def test_hardware_cache_is_invalidated_without_touching_other_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = (
                root
                / "private/var/containers/Shared/SystemGroup/example/Library/Caches/com.apple.MobileGestalt.plist"
            )
            cache.parent.mkdir(parents=True)
            cache.write_bytes(plistlib.dumps({"CacheVersion": "stale"}))
            other = cache.with_name("unrelated.plist")
            other.write_bytes(b"keep")
            self.assertEqual(root_tools.invalidate_capabilities(root), 1)
            self.assertFalse(cache.exists())
            self.assertEqual(other.read_bytes(), b"keep")
            self.assertEqual(root_tools.invalidate_capabilities(root), 0)


if __name__ == "__main__":
    unittest.main()
