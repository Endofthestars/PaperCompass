from __future__ import annotations

from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from fixture_builders import build_mini_paper_notes, initialize_upstream_repository


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SYNC_SCRIPT = SCRIPTS / "sync_paper_notes.sh"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analyzer = load_script("analyze_paper_notes")
trend = load_script("build_trend_report")


class PaperNoteReportTests(unittest.TestCase):
    def test_frontmatter_accepts_scalars_and_rejects_unclosed_blocks(self) -> None:
        self.assertEqual(
            {"title": "中文标题", "code": "value"},
            analyzer.frontmatter(
                '---\ntitle: "中文标题"\ncode: value\n---\n正文\n'
            ),
        )
        self.assertEqual({}, analyzer.frontmatter("---\ntitle: incomplete\n"))
        self.assertEqual({}, analyzer.frontmatter("title: absent delimiters\n"))

    def test_analysis_filters_paths_counts_topics_and_caps_examples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            docs = build_mini_paper_notes(Path(temporary))
            report = analyzer.analyze_corpus(docs)

        self.assertEqual(12, report["paper_files"])
        self.assertEqual(
            [["CVPR2026", 6], ["CVPR2025", 4], ["ACL2026", 2]],
            _json_rows(report["conferences"]),
        )
        self.assertEqual(
            [["vision", 10], ["alpha", 1], ["zeta", 1]],
            _json_rows(report["areas"]),
        )
        topics = dict(report["high_frequency_topics"])
        self.assertEqual(5, topics["生成模型"])
        self.assertEqual(3, topics["可靠性"])
        self.assertEqual(2, topics["具身智能"])
        self.assertNotIn("不应出现", topics)
        self.assertEqual(3, len(report["examples"]["vision"]))
        self.assertEqual("统一视觉标题 续行", report["examples"]["vision"][0])

    def test_analysis_and_markdown_are_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docs = build_mini_paper_notes(root)
            json_path = root / "first" / "report.json"
            markdown_path = root / "first" / "report.md"

            self.assertEqual(0, analyzer.main([str(docs), str(json_path)]))
            self.assertEqual(0, trend.main([str(docs), str(markdown_path)]))
            first_json = json_path.read_bytes()
            first_markdown = markdown_path.read_bytes()

            self.assertEqual(0, analyzer.main([str(docs), str(json_path)]))
            self.assertEqual(0, trend.main([str(docs), str(markdown_path)]))
            self.assertEqual(first_json, json_path.read_bytes())
            self.assertEqual(first_markdown, markdown_path.read_bytes())

    def test_trend_report_applies_threshold_delta_and_stable_ties(self) -> None:
        counts = {
            "CVPR2025": Counter({"zeta": 4, "alpha": 4, "falling": 7}),
            "CVPR2026": Counter({"zeta": 6, "alpha": 6, "falling": 1}),
        }
        report = trend.render_report(counts)
        alpha = "| +2 | `alpha` | 4 | 6 |"
        zeta = "| +2 | `zeta` | 4 | 6 |"
        self.assertLess(report.index(alpha), report.index(zeta))
        self.assertIn("| -6 | `falling` | 7 | 1 |", report)
        self.assertNotIn("below-threshold", report)

    def test_empty_corpus_creates_both_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docs = root / "empty"
            docs.mkdir()
            json_path = root / "nested" / "report.json"
            markdown_path = root / "nested" / "report.md"

            self.assertEqual(0, analyzer.main([str(docs), str(json_path)]))
            self.assertEqual(0, trend.main([str(docs), str(markdown_path)]))

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(0, payload["paper_files"])
            self.assertEqual([], payload["areas"])
            self.assertIn("当前共统计 **0 篇论文**", markdown_path.read_text())

    def test_symlinked_markdown_outside_root_is_never_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docs = root / "docs"
            docs.mkdir()
            outside = root / "secret.md"
            outside.write_text("高频主题：泄露×99\n", encoding="utf-8")
            link = docs / "CVPR2026" / "vision" / "paper.md"
            link.parent.mkdir(parents=True)
            link.symlink_to(outside)

            with mock.patch.object(
                Path,
                "read_text",
                side_effect=AssertionError("symlink target was read"),
            ):
                report = analyzer.analyze_corpus(docs)
                counts = trend.collect_counts(docs)

            self.assertEqual(0, report["paper_files"])
            self.assertEqual({}, counts)

    def test_local_sync_analysis_and_trend_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            upstream = initialize_upstream_repository(root)
            mirror = root / "mirror"
            cache = root / "cache"
            env = os.environ.copy()
            env.update(
                {
                    "PAPER_NOTES_UPSTREAM_URL": str(upstream),
                    "PAPER_NOTES_CACHE_DIR": str(cache),
                }
            )
            sync = subprocess.run(
                ["bash", str(SYNC_SCRIPT), str(mirror)],
                cwd=ROOT,
                env=env,
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, sync.returncode, sync.stderr)

            json_path = root / "reports" / "trends.json"
            markdown_path = root / "reports" / "trends.md"
            self.assertEqual(
                0,
                analyzer.main([str(mirror / "docs"), str(json_path)]),
            )
            self.assertEqual(
                0,
                trend.main([str(mirror / "docs"), str(markdown_path)]),
            )
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(12, payload["paper_files"])
            self.assertIn(
                "### CVPR（4 → 6）",
                markdown_path.read_text(encoding="utf-8"),
            )
            self.assertTrue((mirror / "UPSTREAM.md").is_file())


def _json_rows(value: object) -> object:
    """Normalize tuple rows to their JSON representation for readable assertions."""
    return json.loads(json.dumps(value, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
