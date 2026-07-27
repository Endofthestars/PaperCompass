from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / "scripts" / "sync_paper_notes.sh"


class PaperNotesSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="paper-notes-sync-test-"))
        self.upstream = self.temp_dir / "upstream"
        self.target = self.temp_dir / "target"
        self.cache = self.temp_dir / "cache"
        self.upstream.mkdir()
        self.run_cmd(["git", "init", "--initial-branch=main"])
        self.run_cmd(["git", "config", "user.name", "Test User"])
        self.run_cmd(["git", "config", "user.email", "test@example.com"])
        self.write_upstream("first note")
        self.commit_upstream("initial corpus")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def run_cmd(self, args: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=cwd or self.upstream,
            check=check,
            text=True,
            capture_output=True,
        )

    def sync(self, *, max_file_bytes: int | None = None, upstream: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "PAPER_NOTES_UPSTREAM_URL": str(upstream or self.upstream),
                "PAPER_NOTES_CACHE_DIR": str(self.cache),
            }
        )
        if max_file_bytes is not None:
            env["PAPER_NOTES_MAX_FILE_BYTES"] = str(max_file_bytes)
        return subprocess.run(
            ["bash", str(SYNC_SCRIPT), str(self.target)],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
            env=env,
        )

    def write_upstream(self, body: str) -> None:
        docs = self.upstream / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "note.md").write_text(body, encoding="utf-8")
        (self.upstream / "LICENSE").write_text("CC BY-NC-SA 4.0\n", encoding="utf-8")

    def commit_upstream(self, message: str) -> None:
        self.run_cmd(["git", "add", "docs", "LICENSE"])
        self.run_cmd(["git", "commit", "-m", message])

    def test_initial_sync_copies_docs_license_and_provenance(self) -> None:
        result = self.sync()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("first note", (self.target / "docs" / "note.md").read_text())
        self.assertEqual("CC BY-NC-SA 4.0\n", (self.target / "LICENSE").read_text())
        provenance = (self.target / "UPSTREAM.md").read_text(encoding="utf-8")
        self.assertIn("upstream_commit:", provenance)
        self.assertIn("CC BY-NC-SA 4.0", provenance)

    def test_sync_updates_additions_modifications_and_deletions(self) -> None:
        self.assertEqual(0, self.sync().returncode)
        (self.upstream / "docs" / "note.md").unlink()
        (self.upstream / "docs" / "new.md").write_text("new note", encoding="utf-8")
        self.commit_upstream("replace note")

        result = self.sync()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse((self.target / "docs" / "note.md").exists())
        self.assertEqual("new note", (self.target / "docs" / "new.md").read_text())

    def test_unchanged_revision_does_not_rewrite_metadata(self) -> None:
        self.assertEqual(0, self.sync().returncode)
        metadata_path = self.target / "UPSTREAM.md"
        metadata = metadata_path.read_text(encoding="utf-8")
        timestamp_line = next(
            line for line in metadata.splitlines()
            if line.startswith("- synced_at_utc: ")
        )
        sentinel_line = "- synced_at_utc: 2000-01-01T00:00:00Z"
        metadata_path.write_text(
            metadata.replace(timestamp_line, sentinel_line),
            encoding="utf-8",
        )
        before = metadata_path.read_bytes()
        self.assertEqual(0, self.sync().returncode)
        self.assertEqual(before, metadata_path.read_bytes())

    def test_oversized_file_fails_without_modifying_target(self) -> None:
        self.assertEqual(0, self.sync().returncode)
        before = (self.target / "docs" / "note.md").read_bytes()
        (self.upstream / "docs" / "large.md").write_bytes(b"x" * 2048)
        self.commit_upstream("add large file")

        result = self.sync(max_file_bytes=1024)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("oversized file", result.stderr)
        self.assertEqual(before, (self.target / "docs" / "note.md").read_bytes())
        self.assertFalse((self.target / "docs" / "large.md").exists())

    def test_unavailable_upstream_fails_without_modifying_target(self) -> None:
        self.assertEqual(0, self.sync().returncode)
        before = (self.target / "docs" / "note.md").read_bytes()
        bad_cache = self.temp_dir / "missing-cache"
        self.cache = bad_cache

        result = self.sync(upstream=self.temp_dir / "missing-upstream")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, (self.target / "docs" / "note.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
