"""Installation must be repeatable and preserve any pre-existing component."""

import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "installer", ROOT / "scripts/install_urevo_local.py"
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "configuration.yaml").write_text("default_config:\n")
        self.files = installer.files_at(ROOT / "custom_components/urevo_local")

    def run_install(self, apply=False, upgrade=False):
        with redirect_stdout(StringIO()):
            installer.install(self.files, self.root, apply, upgrade)

    def test_dry_run_does_not_install(self):
        self.run_install()
        self.assertFalse((self.root / "custom_components").exists())

    def test_apply_and_repeat_are_idempotent(self):
        self.run_install(True)
        self.run_install(True)
        target = self.root / "custom_components/urevo_local"
        self.assertEqual(installer.files_at(target), self.files)
        self.assertEqual(
            (target / "translations/en.json").read_bytes(), self.files["strings.json"]
        )

    def test_existing_different_component_is_preserved(self):
        self.run_install(True)
        existing = self.root / "custom_components/urevo_local/protocol.py"
        existing.write_text("# existing user work\n")
        with self.assertRaises(ValueError):
            self.run_install(True)
        self.assertEqual(existing.read_text(), "# existing user work\n")

    def test_upgrade_keeps_verified_rollback_copy_and_receipt(self):
        self.run_install(True)
        original = dict(self.files)
        self.files["protocol.py"] += b"\n# new version\n"
        self.run_install(True, True)
        receipt = json.loads(
            (self.root / ".urevo-local-install-receipt.json").read_text()
        )
        backup = Path(receipt["backup"])
        self.assertEqual(installer.files_at(backup / "urevo_local"), original)
        self.assertTrue((backup / "install-receipt.json").is_file())
        self.assertEqual(
            installer.files_at(self.root / "custom_components/urevo_local"), self.files
        )
        self.run_install(True, True)

    def test_upgrade_dry_run_leaves_original_untouched(self):
        self.run_install(True)
        original = dict(self.files)
        self.files["protocol.py"] += b"\n# new version\n"
        self.run_install(False, True)
        self.assertEqual(
            installer.files_at(self.root / "custom_components/urevo_local"), original
        )
        self.assertEqual(list(self.root.glob(".urevo-backup-*")), [])

    def test_upgrade_preserves_modified_translation(self):
        self.run_install(True)
        translation = self.root / "custom_components/urevo_local/translations/en.json"
        translation.write_text('{"user": "custom translation"}')
        with self.assertRaises(ValueError):
            self.run_install(True, True)
        self.assertEqual(translation.read_text(), '{"user": "custom translation"}')

    def test_upgrade_from_receipt_without_brand_asset(self):
        self.run_install(True)
        target = self.root / "custom_components/urevo_local"
        (target / "brand/icon.png").unlink()
        (target / "brand").rmdir()
        receipt_path = self.root / ".urevo-local-install-receipt.json"
        receipt = json.loads(receipt_path.read_text())
        del receipt["hashes"]["brand/icon.png"]
        receipt_path.write_text(json.dumps(receipt))
        self.run_install(True, True)
        self.assertEqual(
            (target / "brand/icon.png").read_bytes(), self.files["brand/icon.png"]
        )
        backup = Path(json.loads(receipt_path.read_text())["backup"])
        self.assertFalse((backup / "urevo_local/brand/icon.png").exists())

    def test_upgrade_preserves_unknown_file(self):
        self.run_install(True)
        extra = self.root / "custom_components/urevo_local/private.txt"
        extra.write_text("user data")
        with self.assertRaises(ValueError):
            self.run_install(True, True)
        self.assertEqual(extra.read_text(), "user data")

    def test_failed_swap_restores_previous_component(self):
        self.run_install(True)
        original = dict(self.files)
        self.files["protocol.py"] += b"\n# new version\n"
        rename = Path.rename

        def fail_stage(path, target):
            if path.name.startswith(".urevo-stage-"):
                raise OSError("Simulated failed swap")
            return rename(path, target)

        with patch.object(Path, "rename", fail_stage), self.assertRaises(OSError):
            self.run_install(True, True)
        self.assertEqual(
            installer.files_at(self.root / "custom_components/urevo_local"), original
        )


if __name__ == "__main__":
    unittest.main()
