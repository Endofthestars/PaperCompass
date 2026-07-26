"""Bootstrap-grace behavior of hooks/validate-session-state.sh.

Regression background: the documented init order writes session-state.json
before any Markdown artifact exists, so on Claude Code the very first write
always fired the PostToolUse hook and always failed with a wall of
"required artifact is missing" errors. The hook now soft-passes exactly that
window: no artifacts on disk AND no committed controller transition.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "plugins" / "hotspot-to-rq" / "hooks" / "validate-session-state.sh"


class HookBootstrapGraceTests(unittest.TestCase):
    def run_hook(self, file_path: Path) -> subprocess.CompletedProcess[str]:
        payload = json.dumps(
            {"tool_name": "Write", "tool_input": {"file_path": str(file_path)}}
        )
        return subprocess.run(
            ["bash", str(HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
        )

    def make_session(self, state: dict) -> Path:
        root = Path(tempfile.mkdtemp(prefix="hook-bootstrap-"))
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(root)], check=False))
        session_dir = root / "reports" / "research-direction" / "20260726-000001"
        session_dir.mkdir(parents=True)
        state_path = session_dir / "session-state.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        return state_path

    def test_bootstrap_write_soft_passes_before_artifacts_exist(self) -> None:
        state_path = self.make_session(
            {"mainline_control": {"revision": 0, "transition_log": []}}
        )
        completed = self.run_hook(state_path)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("bootstrap", completed.stderr)

    def test_invalid_state_still_fails_once_an_artifact_exists(self) -> None:
        state_path = self.make_session(
            {"mainline_control": {"revision": 0, "transition_log": []}}
        )
        (state_path.parent / "direction-map.md").write_text("stub", encoding="utf-8")
        completed = self.run_hook(state_path)
        self.assertEqual(2, completed.returncode)
        self.assertTrue(completed.stderr.strip())

    def test_invalid_state_still_fails_after_a_committed_transition(self) -> None:
        state_path = self.make_session(
            {
                "mainline_control": {
                    "revision": 1,
                    "transition_log": [{"revision": 1, "checkpoint": "SESSION_INIT"}],
                }
            }
        )
        completed = self.run_hook(state_path)
        self.assertEqual(2, completed.returncode)
        self.assertTrue(completed.stderr.strip())

    def test_unrelated_writes_are_ignored(self) -> None:
        completed = self.run_hook(Path("/tmp/not-a-session/notes.md"))
        self.assertEqual(0, completed.returncode, completed.stderr)


if __name__ == "__main__":
    unittest.main()
