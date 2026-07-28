from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PINNED_CODEX_SHA = "61a44880a85d2fd0d8770908dea5733495e571c8"
PINNED_CLAUDE_CODE = "2.1.220"
PINNED_COVERAGE = "7.15.2"
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

    def test_python_matrix_reports_branch_coverage_without_a_threshold(self) -> None:
        workflow = (WORKFLOWS / "plugin-ci.yml").read_text(encoding="utf-8")
        test_script = (ROOT / "scripts" / "test_plugin.sh").read_text(
            encoding="utf-8"
        )
        coverage_config = (ROOT / ".coveragerc").read_text(encoding="utf-8")
        self.assertIn(f"coverage=={PINNED_COVERAGE}", workflow)
        self.assertIn('PYTHON_COVERAGE: "1"', workflow)
        self.assertIn("python -m coverage report --show-missing", workflow)
        self.assertIn("python -m coverage xml", workflow)
        self.assertIn("python -m coverage html", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("PYTHON_COVERAGE", test_script)
        self.assertIn("-m coverage run --branch", test_script)
        self.assertIn("branch = True", coverage_config)
        self.assertNotIn("fail-under", workflow)
        self.assertNotIn("fail_under", coverage_config)

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

    def test_paper_notes_sync_is_scheduled_manual_and_uses_a_gated_pr(self) -> None:
        workflow = (WORKFLOWS / "sync-paper-notes.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "17 7 * * 1"', workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("actions: write", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("pull-requests: write", workflow)
        self.assertIn("group: sync-paper-notes-main", workflow)
        self.assertIn("PAPER_NOTES_CACHE_DIR: ${{ runner.temp }}/paper-notes-upstream", workflow)
        self.assertIn("bash scripts/sync_paper_notes.sh", workflow)
        self.assertIn("git status --porcelain -- data/Paper-Notes", workflow)
        self.assertIn(
            "git diff --cached --check -- data/Paper-Notes/UPSTREAM.md", workflow
        )
        self.assertNotIn("git diff --cached --check\n", workflow)
        self.assertIn("git commit --quiet", workflow)
        self.assertIn("SYNC_BRANCH: automation/paper-notes-sync", workflow)
        self.assertIn("git push --force-with-lease", workflow)
        self.assertIn("gh pr create", workflow)
        self.assertIn('gh pr edit "$pr_url"', workflow)
        self.assertIn("gh workflow run plugin-ci.yml", workflow)
        self.assertIn('gh pr merge "$PR_URL"', workflow)
        self.assertIn("--auto --squash --delete-branch", workflow)
        self.assertNotIn("git push origin HEAD:main", workflow)


if __name__ == "__main__":
    unittest.main()
