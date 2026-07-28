#!/usr/bin/env python3
"""Build the human-readable Paper-Notes trend report."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re
from typing import Mapping


DEFAULT_ROOT = Path("data/Paper-Notes/docs")
DEFAULT_OUT = Path("reports/trend-report.md")
VALID_CONFERENCE = re.compile(
    r"(?:ACL|AAAI|CVPR|ECCV|ICCV|ICLR|ICML|NeurIPS)\d{4}"
)


def collect_counts(root: Path) -> dict[str, Counter[str]]:
    """Count paper Markdown files by conference and area."""
    counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    paths = sorted(
        root.glob("**/*.md"),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    for path in paths:
        if path.is_symlink():
            continue
        rel = path.relative_to(root)
        if len(rel.parts) < 3 or path.name in {"index.md", "search.md"}:
            continue
        conf, field = rel.parts[:2]
        if VALID_CONFERENCE.fullmatch(conf):
            counts[conf][field] += 1
    return dict(counts)


def _total(counts: Mapping[str, Counter[str]], conference: str) -> int:
    return sum(counts.get(conference, Counter()).values())


def render_report(counts: Mapping[str, Counter[str]]) -> str:
    """Render deterministic Markdown from precomputed counts."""
    comparisons: list[tuple[str, str, str, list[tuple[int, str, int, int]]]] = []
    for conf in ("CVPR", "ACL", "ICML"):
        old, new = f"{conf}2025", f"{conf}2026"
        old_counts = counts.get(old, Counter())
        new_counts = counts.get(new, Counter())
        fields = set(old_counts) | set(new_counts)
        rows = []
        for field in fields:
            before, after = old_counts[field], new_counts[field]
            if before + after >= 8:
                rows.append((after - before, field, before, after))
        rows.sort(key=lambda row: (-row[0], row[1]))
        comparisons.append((conf, old, new, rows))

    lines = [
        "# PaperNotes 论文热点趋势报告",
        "",
        "> 数据源：zhaoyang97/Paper-Notes；生成时间：2026-07-22。",
        "",
        "## 数据概况",
        "",
        (
            f"当前共统计 **{sum(_total(counts, conf) for conf in counts)} 篇论文**，"
            f"覆盖 **{len(counts)} 个会议**。"
        ),
        "",
        "## 2025 → 2026 领域变化",
        "",
    ]
    for conf, old, new, rows in comparisons:
        lines.extend(
            [
                f"### {conf}（{_total(counts, old)} → {_total(counts, new)}）",
                "",
                "| 变化 | 领域 | 2025 | 2026 |",
                "|---:|---|---:|---:|",
            ]
        )
        for delta, field, before, after in rows[:10]:
            lines.append(f"| {delta:+d} | `{field}` | {before} | {after} |")
        lines.append("")

    lines.extend(
        [
            "## 初步判断",
            "",
            "### 高热但竞争激烈",
            "",
            "- 图像生成、3D 视觉、多模态 VLM：论文基数最大，适合做综述、基准、效率和可靠性方向。",
            "- 强化学习、模型压缩：数量大且持续出现，单纯提出小改进的空间较小。",
            "",
            "### 值得重点寻找空白",
            "",
            "- LLM Agent 的可靠性、成本、长程任务和安全评测。",
            "- 多模态模型的推理效率、数据质量和真实场景泛化。",
            "- 具身智能与 Agent 的交叉：规划、工具使用、记忆和多智能体协作。",
            "- AI 安全与实际部署结合，而不是只做静态攻击展示。",
            "",
            "## 下一步选题筛选规则",
            "",
            "1. 优先选择增长明显但总量尚未饱和的领域。",
            "2. 检查论文是否有公开代码、数据集和可复现实验。",
            "3. 优先寻找跨会议重复出现、但评测标准不统一的问题。",
            "4. 每个候选主题至少阅读 10 篇代表性论文后再决定是否投入。",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(report: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")


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
        help=f"Markdown report path (default: {DEFAULT_OUT})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    write_report(render_report(collect_counts(args.root)), args.output)
    print(f"写入 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
