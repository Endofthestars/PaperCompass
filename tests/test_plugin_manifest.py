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
    # Mirror of the upstream ingestion validator pinned in CI
    # (openai/codex@61a44880, plugin-creator/scripts/validate_plugin.py).
    # Unknown manifest fields are rejected upstream — `hooks`, `workflows`,
    # and `agents` are Claude-only and must never migrate into this manifest.
    UPSTREAM_MANIFEST_FIELDS = {
        "id",
        "name",
        "version",
        "description",
        "skills",
        "apps",
        "mcpServers",
        "interface",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
    }
    UPSTREAM_INTERFACE_FIELDS = {
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
        "capabilities",
        "websiteURL",
        "privacyPolicyURL",
        "termsOfServiceURL",
        "brandColor",
        "composerIcon",
        "logo",
        "logoDark",
        "screenshots",
        "defaultPrompt",
        "default_prompt",
    }

    def test_manifest_declares_a_loadable_skill_and_interface(self) -> None:
        manifest = load_json(CODEX_MANIFEST)
        self.assertEqual("hotspot-to-rq", manifest["name"])
        self.assertTrue(manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertTrue(SKILL_FILE.is_file())

        interface = manifest["interface"]
        # Upstream requires all five of these as non-empty strings.
        for field in (
            "displayName",
            "shortDescription",
            "longDescription",
            "developerName",
            "category",
        ):
            self.assertTrue(interface[field].strip(), field)
        self.assertTrue(interface["defaultPrompt"])
        self.assertIn("Research", interface["capabilities"])

    def test_manifest_uses_only_upstream_accepted_fields(self) -> None:
        manifest = load_json(CODEX_MANIFEST)
        self.assertLessEqual(set(manifest), self.UPSTREAM_MANIFEST_FIELDS)
        self.assertLessEqual(
            set(manifest["interface"]), self.UPSTREAM_INTERFACE_FIELDS
        )

    def test_default_prompts_are_short_starter_entries(self) -> None:
        # Upstream spec: defaultPrompt is an array of at most 3 starter
        # prompts; entries past 3 are ignored and each entry is truncated at
        # 128 characters, so longer prompts would ship visibly broken UX.
        prompts = load_json(CODEX_MANIFEST)["interface"]["defaultPrompt"]
        self.assertIsInstance(prompts, list)
        self.assertTrue(1 <= len(prompts) <= 3)
        for prompt in prompts:
            self.assertIsInstance(prompt, str)
            self.assertTrue(prompt.strip())
            self.assertLessEqual(len(prompt), 128)

    def test_version_is_strict_semver_with_codex_cachebuster(self) -> None:
        # update_plugin_cachebuster.py writes `<semver>+codex.<token>` where
        # the token is sanitized to lowercase alphanumerics and hyphens. The
        # semver core mirrors upstream SEMVER_RE: no leading zeros, and an
        # optional prerelease that the cachebuster script preserves.
        version = load_json(CODEX_MANIFEST)["version"]
        number = r"(?:0|[1-9]\d*)"
        prerelease_id = r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
        self.assertRegex(
            version,
            rf"^{number}\.{number}\.{number}"
            rf"(?:-{prerelease_id}(?:\.{prerelease_id})*)?"
            rf"\+codex\.[a-z0-9-]+$",
        )


class ClaudeManifestTests(unittest.TestCase):
    def test_manifest_identifies_the_plugin(self) -> None:
        manifest = load_json(CLAUDE_MANIFEST)
        self.assertEqual("hotspot-to-rq", manifest["name"])
        self.assertTrue(manifest["displayName"])
        self.assertTrue(manifest["version"])
        self.assertTrue(manifest["description"])
        self.assertTrue(manifest["author"]["name"])

    def test_manifest_relies_on_default_component_discovery(self) -> None:
        # Claude Code auto-discovers skills/, agents/, and hooks/hooks.json.
        # Re-declaring hooks in the manifest is not redundant but fatal: the
        # runtime rejects the duplicate ("Duplicate hooks file detected") and
        # the WHOLE plugin fails to load, while `plugin validate --strict`
        # stays green. Reproduced live on claude 2.1.220 (BUGS.md P-01).
        # workflows/ is the one path that must stay declared (see
        # PluginWorkflowTests); a loaded plugin with it declared was verified
        # alongside the P-01 fix.
        manifest = load_json(CLAUDE_MANIFEST)
        for key in ("skills", "commands", "agents", "mcpServers", "hooks"):
            self.assertNotIn(key, manifest)
        self.assertTrue((PLUGIN_ROOT / "hooks" / "hooks.json").is_file())
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

    def test_manifests_share_keywords_and_source_metadata(self) -> None:
        codex = load_json(CODEX_MANIFEST)
        claude = load_json(CLAUDE_MANIFEST)
        self.assertEqual(codex["keywords"], claude["keywords"])
        self.assertEqual(codex["homepage"], claude["homepage"])
        self.assertEqual(codex["repository"], claude["repository"])

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

    def run_hook_payload(self, payload: dict) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT))
        return subprocess.run(
            [str(self.HOOK_SCRIPT)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def run_hook(self, file_path: str) -> subprocess.CompletedProcess[str]:
        return self.run_hook_payload(
            {"tool_name": "Write", "tool_input": {"file_path": file_path}}
        )

    def test_hook_wiring_targets_all_write_paths(self) -> None:
        # Bash is matched too: shell-redirect writes bypassed the hook when
        # only Write|Edit were matched, and on Codex file edits arrive as
        # apply_patch (alias Edit|Write) with the patch text in
        # tool_input.command instead of a file_path.
        config = load_json(PLUGIN_ROOT / "hooks" / "hooks.json")
        entry = config["hooks"]["PostToolUse"][0]
        self.assertEqual("Write|Edit|Bash", entry["matcher"])
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
            # An artifact on disk ends the bootstrap-grace window (see
            # tests/test_hook_bootstrap.py for the grace behavior itself).
            (session_dir / "direction-map.md").write_text("stub", encoding="utf-8")
            result = self.run_hook(str(state_path))
        self.assertEqual(2, result.returncode)
        self.assertIn("Session validation failed", result.stderr)

    def make_invalid_session(self, tmp: str) -> Path:
        session_dir = Path(tmp) / "reports" / "research-direction" / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "session-state.json").write_text("{}", encoding="utf-8")
        (session_dir / "direction-map.md").write_text("stub", encoding="utf-8")
        return session_dir / "session-state.json"

    def test_hook_catches_codex_apply_patch_writes(self) -> None:
        # Codex delivers file edits as apply_patch with the patch text in
        # tool_input.command and NO file_path; the hook must not go inert.
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.make_invalid_session(tmp)
            patch = (
                "*** Begin Patch\n"
                f"*** Update File: {state_path}\n"
                "@@\n+{}\n"
                "*** End Patch"
            )
            result = self.run_hook_payload(
                {"tool_name": "apply_patch", "tool_input": {"command": patch}}
            )
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("Session validation failed", result.stderr)

    def test_hook_catches_bash_writes_mentioning_session_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.make_invalid_session(tmp)
            command = f"printf '{{}}' > {state_path}"
            result = self.run_hook_payload(
                {"tool_name": "Bash", "tool_input": {"command": command}}
            )
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("Session validation failed", result.stderr)

    def test_hook_ignores_bash_commands_without_session_paths(self) -> None:
        result = self.run_hook_payload(
            {"tool_name": "Bash", "tool_input": {"command": "ls -la && git status"}}
        )
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stderr)

    def test_hook_fails_closed_when_validator_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.make_invalid_session(tmp)
            payload = json.dumps(
                {"tool_name": "Write", "tool_input": {"file_path": str(state_path)}}
            )
            env = dict(os.environ, CLAUDE_PLUGIN_ROOT="/nonexistent-plugin-root")
            result = subprocess.run(
                [str(self.HOOK_SCRIPT)],
                input=payload,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
        self.assertEqual(2, result.returncode)
        self.assertIn("misconfigured", result.stderr)


class RuntimeLoadTests(unittest.TestCase):
    # P-01 regression: `claude plugin validate --strict` and every shape test
    # stayed green while the runtime refused to load the plugin outright
    # (duplicate hooks declaration). Shape tests cannot see load failures, so
    # when a local claude CLI has the plugin installed, ask the runtime.

    def test_installed_plugin_reports_no_load_failure(self) -> None:
        claude = shutil.which(os.environ.get("CLAUDE_CODE_BIN", "claude"))
        if claude is None:
            self.skipTest("claude CLI is not installed")
        result = subprocess.run(
            [claude, "plugin", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if result.returncode != 0:
            self.skipTest("claude plugin list is unavailable here")
        if "hotspot-to-rq" not in result.stdout:
            self.skipTest("hotspot-to-rq is not installed locally")
        self.assertNotIn("failed to load", result.stdout, result.stdout)


class SkillAgentYamlTests(unittest.TestCase):
    AGENT_YAML = (
        PLUGIN_ROOT
        / "skills"
        / "research-direction-debate"
        / "agents"
        / "openai.yaml"
    )

    def load(self) -> dict:
        try:
            import yaml
        except ImportError:  # pragma: no cover - CI always installs PyYAML
            self.skipTest("PyYAML is not installed")
        return yaml.safe_load(self.AGENT_YAML.read_text(encoding="utf-8"))

    def test_agent_yaml_uses_only_upstream_accepted_fields(self) -> None:
        # Mirror of validate_skill_agent_manifest in the pinned upstream
        # validator: unknown keys fail Codex plugin ingestion.
        payload = self.load()
        self.assertLessEqual(
            set(payload), {"interface", "policy", "dependencies"}
        )
        self.assertLessEqual(
            set(payload["interface"]),
            {
                "display_name",
                "short_description",
                "icon_small",
                "icon_large",
                "brand_color",
                "default_prompt",
            },
        )

    def test_interface_matches_upstream_ux_constraints(self) -> None:
        interface = self.load()["interface"]
        self.assertTrue(interface["display_name"].strip())
        # Upstream guidance: 25-64 chars so the blurb scans in the UI.
        self.assertTrue(25 <= len(interface["short_description"]) <= 64)
        # Upstream requires the default prompt to name the skill as $<name>.
        self.assertIn(
            "$research-direction-debate", interface["default_prompt"]
        )

    def test_implicit_invocation_is_pinned_on(self) -> None:
        # Natural-language routing parity with the Claude runtime: the
        # upstream default is already true, but pinning it keeps a future
        # default flip from silently disabling description-based routing.
        self.assertIs(True, self.load()["policy"]["allow_implicit_invocation"])


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
