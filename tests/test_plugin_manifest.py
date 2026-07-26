from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
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
        # Hooks are the exception: declared explicitly so the enforcement layer
        # cannot be lost to auto-discovery changes.
        manifest = load_json(CLAUDE_MANIFEST)
        for key in ("skills", "commands", "agents", "mcpServers"):
            self.assertNotIn(key, manifest)
        self.assertEqual("./hooks/hooks.json", manifest["hooks"])
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
    # Exact single-line whitelists. Claude Code refuses to launch an agent
    # whose tools list resolves to nothing (and `claude plugin validate` does
    # not catch that), and the mainline-controller contract forbids any
    # content, write, or network tool — so the whitelists are pinned verbatim.
    # If an agent legitimately changes tools, update this table deliberately.
    EXPECTED_TOOLS = {
        "mainline-controller.md": "Glob",
        "research-role.md": "Read",
        "search-verification.md": "Read, WebSearch, WebFetch",
    }

    def test_bundled_agents_match_the_pinned_tool_whitelists(self) -> None:
        agent_files = sorted((PLUGIN_ROOT / "agents").glob("*.md"))
        self.assertEqual(
            sorted(self.EXPECTED_TOOLS),
            [path.name for path in agent_files],
        )
        for path in agent_files:
            with self.subTest(agent=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                frontmatter = text.split("---\n", 2)[1]
                lines = frontmatter.splitlines()
                self.assertIn(f"tools: {self.EXPECTED_TOOLS[path.name]}", lines)
                self.assertTrue(
                    any(line.startswith("maxTurns: ") for line in lines)
                )
                self.assertTrue(
                    any(
                        line.startswith("name: ") and line.split(": ", 1)[1].strip()
                        for line in lines
                    )
                )
                self.assertTrue(
                    any(
                        line.startswith("description: ")
                        and line.split(": ", 1)[1].strip()
                        for line in lines
                    )
                )


class PluginWorkflowTests(unittest.TestCase):
    WORKFLOW = PLUGIN_ROOT / "workflows" / "dispatch-batch.js"

    def test_manifest_declares_the_workflows_directory(self) -> None:
        manifest = load_json(CLAUDE_MANIFEST)
        self.assertEqual("./workflows/", manifest["workflows"])
        self.assertTrue(self.WORKFLOW.is_file())

    def test_workflow_meta_matches_its_filename(self) -> None:
        source = self.WORKFLOW.read_text(encoding="utf-8")
        self.assertTrue(source.startswith("export const meta = {"))
        self.assertIn("name: 'dispatch-batch'", source)
        self.assertIn("description:", source)

    def test_workflow_body_parses_in_an_async_function_context(self) -> None:
        # The workflow runtime executes the script body inside an async
        # function (top-level await and return are legal there), so plain
        # `node --check` cannot be used.
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        script = (
            "const fs = require('fs');"
            f"const src = fs.readFileSync({str(self.WORKFLOW)!r}, 'utf8');"
            "const body = src.replace(/^export const meta/m, 'const meta');"
            "const AsyncFunction ="
            "  Object.getPrototypeOf(async function () {}).constructor;"
            "new AsyncFunction("
            "  'agent', 'pipeline', 'parallel', 'phase', 'log',"
            "  'args', 'budget', 'workflow', body);"
        )
        result = subprocess.run(
            [node, "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(0, result.returncode, result.stderr)


class SessionStateHookTests(unittest.TestCase):
    HOOK_SCRIPT = PLUGIN_ROOT / "hooks" / "validate-session-state.sh"

    def run_hook(self, file_path: str) -> subprocess.CompletedProcess[str]:
        payload = json.dumps(
            {"tool_name": "Write", "tool_input": {"file_path": file_path}}
        )
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT))
        return subprocess.run(
            [str(self.HOOK_SCRIPT)],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_hook_wiring_targets_write_and_edit(self) -> None:
        config = load_json(PLUGIN_ROOT / "hooks" / "hooks.json")
        entry = config["hooks"]["PostToolUse"][0]
        self.assertEqual("Write|Edit", entry["matcher"])
        self.assertEqual(
            "${CLAUDE_PLUGIN_ROOT}/hooks/validate-session-state.sh",
            entry["hooks"][0]["command"],
        )
        self.assertTrue(os.access(self.HOOK_SCRIPT, os.X_OK))

    def test_hook_ignores_unrelated_writes(self) -> None:
        result = self.run_hook("/tmp/unrelated.txt")
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stderr)

    def test_hook_reports_an_invalid_session_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "reports" / "research-direction" / "s1"
            session_dir.mkdir(parents=True)
            state_path = session_dir / "session-state.json"
            state_path.write_text("{}", encoding="utf-8")
            result = self.run_hook(str(state_path))
        self.assertEqual(2, result.returncode)
        self.assertIn("Session validation failed", result.stderr)


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
