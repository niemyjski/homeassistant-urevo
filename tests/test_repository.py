"""Check the installable component's metadata and translation contract."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/urevo_local"


class RepositoryTests(unittest.TestCase):
    def test_translation_matches_source(self):
        self.assertEqual(
            json.loads((COMPONENT / "strings.json").read_text()),
            json.loads((COMPONENT / "translations/en.json").read_text()),
        )

    def test_metadata_matches_installation(self):
        manifest = json.loads((COMPONENT / "manifest.json").read_text())
        self.assertEqual(manifest["domain"], COMPONENT.name)
        self.assertEqual(manifest["codeowners"], ["@niemyjski"])
        self.assertEqual(
            manifest["bluetooth"], [{"local_name": "URTM041", "connectable": True}]
        )
        self.assertTrue(manifest["config_flow"])
        hacs = json.loads((ROOT / "hacs.json").read_text())
        requirements = (ROOT / "requirements-ha.txt").read_text()
        self.assertIn("homeassistant==" + hacs["homeassistant"], requirements)
