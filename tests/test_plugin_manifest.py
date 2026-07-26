from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "hotspot-to-rq"
CODEX_MANIFEST = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
CLAUDE_MANIFEST = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
CODEX_MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
CLAUDE_MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
SKILL_FILE = PLUGIN_ROOT / "skills" / "research-direction-debate" / "SKILL.md"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def base_version(version: str) -> str:
    return version.split("+", 1)[0]


class CodexManifestTests(unittest.TestCase):
    def test_manifest_declares_a_loadable_skill_and_interface(self) -> None:
        manifest = load_json(CODEX_MANIFEST)
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


class ClaudeManifestTests(unittest.TestCase):
    def test_manifest_identifies_the_plugin(self) -> None:
        manifest = load_json(CLAUDE_MANIFEST)
        self.assertEqual("hotspot-to-rq", manifest["name"])
        self.assertTrue(manifest["displayName"])
        self.assertTrue(manifest["version"])
        self.assertTrue(manifest["description"])
        self.assertTrue(manifest["author"]["name"])

    def test_manifest_relies_on_default_skill_discovery(self) -> None:
        # Claude Code scans skills/ by default; declaring the same path again
        # would be redundant, so the manifest must not override component paths.
        manifest = load_json(CLAUDE_MANIFEST)
        for key in ("skills", "commands", "agents", "hooks", "mcpServers"):
            self.assertNotIn(key, manifest)
        self.assertTrue(SKILL_FILE.is_file())


class ManifestParityTests(unittest.TestCase):
    def test_manifests_share_identity_and_base_version(self) -> None:
        codex = load_json(CODEX_MANIFEST)
        claude = load_json(CLAUDE_MANIFEST)
        self.assertEqual(codex["name"], claude["name"])
        self.assertEqual(codex["description"], claude["description"])
        self.assertEqual(codex["author"]["name"], claude["author"]["name"])
        self.assertEqual(
            base_version(codex["version"]), base_version(claude["version"])
        )
        self.assertEqual(
            codex["interface"]["displayName"], claude["displayName"]
        )

    def test_marketplaces_expose_the_same_plugin(self) -> None:
        codex = load_json(CODEX_MARKETPLACE)
        claude = load_json(CLAUDE_MARKETPLACE)
        self.assertEqual("personal", codex["name"])
        self.assertEqual("personal", claude["name"])

        codex_entry = codex["plugins"][0]
        claude_entry = claude["plugins"][0]
        self.assertEqual("hotspot-to-rq", codex_entry["name"])
        self.assertEqual("hotspot-to-rq", claude_entry["name"])
        self.assertEqual("./plugins/hotspot-to-rq", codex_entry["source"]["path"])
        self.assertEqual("./plugins/hotspot-to-rq", claude_entry["source"])
        self.assertTrue(claude["owner"]["name"])


class PluginAgentTests(unittest.TestCase):
    def test_agents_declare_launchable_tool_whitelists(self) -> None:
        # Claude Code refuses to launch an agent whose tools list resolves to
        # nothing (and `claude plugin validate` does not catch it), so every
        # bundled agent must whitelist at least one real tool.
        agent_files = sorted((PLUGIN_ROOT / "agents").glob("*.md"))
        self.assertTrue(agent_files, "no bundled plugin agents found")
        for path in agent_files:
            with self.subTest(agent=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                frontmatter = text.split("---\n", 2)[1]
                fields = {
                    line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip()
                    for line in frontmatter.splitlines()
                    if ":" in line
                }
                self.assertTrue(fields.get("name"))
                self.assertTrue(fields.get("description"))
                tools = fields.get("tools", "")
                self.assertTrue(tools)
                self.assertNotEqual("[]", tools)

    def test_controller_agent_cannot_read_write_or_search(self) -> None:
        # The Mainline Workflow Controller contract forbids inspecting files,
        # editing state, or external retrieval; its whitelist must not grant
        # content access even accidentally.
        text = (PLUGIN_ROOT / "agents" / "mainline-controller.md").read_text(
            encoding="utf-8"
        )
        frontmatter = text.split("---\n", 2)[1]
        tools_line = next(
            line for line in frontmatter.splitlines() if line.startswith("tools:")
        )
        for forbidden in ("Read", "Write", "Edit", "Bash", "WebFetch", "WebSearch"):
            self.assertNotIn(forbidden, tools_line)


class SkillFrontmatterTests(unittest.TestCase):
    def test_skill_has_required_frontmatter(self) -> None:
        skill = SKILL_FILE.read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\n"))
        frontmatter, _body = skill.split("---\n", 2)[1:]
        self.assertIn("name: research-direction-debate", frontmatter)
        self.assertIn("description:", frontmatter)

    def test_skill_description_is_runtime_neutral(self) -> None:
        # One SKILL.md serves both Codex and Claude Code; naming either
        # runtime in the routing description would misroute the other.
        frontmatter = SKILL_FILE.read_text(encoding="utf-8").split("---\n", 2)[1]
        self.assertNotIn("Codex", frontmatter)
        self.assertNotIn("Claude", frontmatter)


if __name__ == "__main__":
    unittest.main()
