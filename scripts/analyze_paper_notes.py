#!/usr/bin/env python3
"""Build a lightweight trend report from Paper-Notes Markdown files."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from typing import Iterable


DEFAULT_ROOT = Path("data/Paper-Notes/docs")
DEFAULT_OUT = Path("reports/paper-notes-trends.json")
VALID_CONFERENCE = re.compile(
    r"(?:ACL|AAAI|CVPR|ECCV|ICCV|ICLR|ICML|NeurIPS)\d{4}"
)
TOPIC_PATTERN = re.compile(r"([^：·]+?)[×x](\d+)")


def frontmatter(text: str) -> dict[str, str]:
    """Parse the intentionally small scalar subset used by Paper-Notes."""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data: dict[str, str] = {}
    for line in parts[1].splitlines():
        match = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if match:
            data[match.group(1)] = match.group(2).strip().strip('"')
    return data


def _stable_counts(counter: Counter[str], limit: int | None = None) -> list[tuple[str, int]]:
    rows = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return rows if limit is None else rows[:limit]


def _record_topics(lines: Iterable[str], keywords: Counter[str]) -> None:
    for line in lines:
        if "高频主题" not in line:
            continue
        for word, count in TOPIC_PATTERN.findall(line):
            normalized = word.strip()
            if normalized:
                keywords[normalized] += int(count)


def analyze_corpus(root: Path) -> dict[str, object]:
    """Analyze one corpus root without reading or writing outside that root."""
    files = sorted(
        root.glob("**/*.md"),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    conference: Counter[str] = Counter()
    area: Counter[str] = Counter()
    keywords: Counter[str] = Counter()
    examples: defaultdict[str, list[str]] = defaultdict(list)

    for path in files:
        if path.is_symlink():
            continue
        rel = path.relative_to(root)
        if len(rel.parts) < 2 or path.name == "search.md":
            continue
        conf, field = rel.parts[0], rel.parts[1]
        if not VALID_CONFERENCE.fullmatch(conf):
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        if path.name == "index.md":
            _record_topics(text.splitlines(), keywords)
            continue

        conference[conf] += 1
        area[field] += 1
        meta = frontmatter(text)
        title = meta.get("title", path.stem).replace("\\n", " ")
        _record_topics(text.splitlines(), keywords)
        if len(examples[field]) < 3:
            examples[field].append(title)

    return {
        "source": str(root),
        "markdown_files": len(files),
        "paper_files": sum(conference.values()),
        "conferences": _stable_counts(conference),
        "areas": _stable_counts(area),
        "high_frequency_topics": _stable_counts(keywords, 30),
        "examples": {
            field: examples[field]
            for field in sorted(examples)
        },
    }


def write_report(report: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"Paper-Notes docs root (default: {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=DEFAULT_OUT,
        help=f"JSON report path (default: {DEFAULT_OUT})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = analyze_corpus(args.root)
    write_report(report, args.output)
    print(
        f"写入 {args.output}: {report['paper_files']} 篇论文，"
        f"{len(report['conferences'])} 个会议，{len(report['areas'])} 个领域"
    )
    print("会议:", report["conferences"])
    print("领域 Top 15:", report["areas"][:15])
    print("主题 Top 15:", report["high_frequency_topics"][:15])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
