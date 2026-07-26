from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PINNED_CODEX_SHA = "61a44880a85d2fd0d8770908dea5733495e571c8"
PINNED_CLAUDE_CODE = "2.1.220"
SETUP_PYTHON_ACTION = "actions/setup-python@v7"


class CiWorkflowTests(unittest.TestCase):
    def test_blocking_ci_pins_official_codex_validators(self) -> None:
        workflow = (WORKFLOWS / "plugin-ci.yml").read_text(encoding="utf-8")
        self.assertIn("repository: openai/codex", workflow)
        self.assertIn(f"ref: {PINNED_CODEX_SHA}", workflow)
        self.assertIn("CODEX_PLUGIN_VALIDATOR:", workflow)
        self.assertIn("CODEX_SKILL_VALIDATOR:", workflow)
        self.assertIn(SETUP_PYTHON_ACTION, workflow)
        self.assertNotIn("continue-on-error", workflow)

    def test_blocking_ci_validates_the_claude_code_plugin(self) -> None:
        workflow = (WORKFLOWS / "plugin-ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            f"curl -fsSL https://claude.ai/install.sh | bash -s {PINNED_CLAUDE_CODE}",
            workflow,
        )
        self.assertIn("claude plugin validate plugins/hotspot-to-rq --strict", workflow)
        self.assertIn("claude plugin validate . --strict", workflow)

    def test_scheduled_compatibility_ci_tracks_main_without_pr_trigger(self) -> None:
        workflow = (WORKFLOWS / "upstream-codex-compat.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("schedule:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("repository: openai/codex", workflow)
        self.assertIn("ref: main", workflow)
        self.assertIn(SETUP_PYTHON_ACTION, workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("continue-on-error", workflow)


if __name__ == "__main__":
    unittest.main()
