from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = ROOT / "plugins" / "hotspot-to-rq" / ".codex-plugin" / "plugin.json"
SKILL_FILE = ROOT / "plugins" / "hotspot-to-rq" / "skills" / "research-direction-debate" / "SKILL.md"


class PluginManifestTests(unittest.TestCase):
    def test_manifest_declares_a_loadable_skill_and_interface(self) -> None:
        manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual("hotspot-to-rq", manifest["name"])
        self.assertTrue(manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertTrue(SKILL_FILE.is_file())

        interface = manifest["interface"]
        self.assertTrue(interface["displayName"])
        self.assertTrue(interface["shortDescription"])
        self.assertTrue(interface["longDescription"])
        self.assertTrue(interface["defaultPrompt"])
        self.assertIn("Research", interface["capabilities"])

    def test_skill_has_required_frontmatter(self) -> None:
        skill = SKILL_FILE.read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\n"))
        frontmatter, _body = skill.split("---\n", 2)[1:]
        self.assertIn("name: research-direction-debate", frontmatter)
        self.assertIn("description:", frontmatter)


if __name__ == "__main__":
    unittest.main()
