#!/usr/bin/env python3
from collections import Counter, defaultdict
from pathlib import Path
import re

ROOT = Path("data/Paper-Notes/docs")
OUT = Path("reports/trend-report.md")
valid = re.compile(r"(?:ACL|AAAI|CVPR|ECCV|ICCV|ICLR|ICML|NeurIPS)\d{4}")

counts = defaultdict(Counter)
for p in ROOT.glob("**/*.md"):
    rel = p.relative_to(ROOT)
    if len(rel.parts) < 3 or p.name == "index.md":
        continue
    conf, field = rel.parts[:2]
    if valid.fullmatch(conf):
        counts[conf][field] += 1

def total(conf):
    return sum(counts[conf].values())

comparisons = []
for conf in ("CVPR", "ACL", "ICML"):
    old, new = f"{conf}2025", f"{conf}2026"
    fields = set(counts[old]) | set(counts[new])
    rows = []
    for field in fields:
        a, b = counts[old][field], counts[new][field]
        if a + b >= 8:
            rows.append((b - a, field, a, b))
    comparisons.append((conf, old, new, sorted(rows, reverse=True)))

lines = ["# PaperNotes 论文热点趋势报告", "", "> 数据源：zhaoyang97/Paper-Notes；生成时间：2026-07-22。", ""]
lines += ["## 数据概况", "", f"当前共统计 **{sum(total(c) for c in counts)} 篇论文**，覆盖 **{len(counts)} 个会议**。", ""]
lines += ["## 2025 → 2026 领域变化", ""]
for conf, old, new, rows in comparisons:
    lines += [f"### {conf}（{total(old)} → {total(new)}）", "", "| 变化 | 领域 | 2025 | 2026 |", "|---:|---|---:|---:|"]
    for delta, field, a, b in rows[:10]:
        lines.append(f"| {delta:+d} | `{field}` | {a} | {b} |")
    lines.append("")

lines += ["## 初步判断", "", "### 高热但竞争激烈", "", "- 图像生成、3D 视觉、多模态 VLM：论文基数最大，适合做综述、基准、效率和可靠性方向。", "- 强化学习、模型压缩：数量大且持续出现，单纯提出小改进的空间较小。", "", "### 值得重点寻找空白", "", "- LLM Agent 的可靠性、成本、长程任务和安全评测。", "- 多模态模型的推理效率、数据质量和真实场景泛化。", "- 具身智能与 Agent 的交叉：规划、工具使用、记忆和多智能体协作。", "- AI 安全与实际部署结合，而不是只做静态攻击展示。", "", "## 下一步选题筛选规则", "", "1. 优先选择增长明显但总量尚未饱和的领域。", "2. 检查论文是否有公开代码、数据集和可复现实验。", "3. 优先寻找跨会议重复出现、但评测标准不统一的问题。", "4. 每个候选主题至少阅读 10 篇代表性论文后再决定是否投入。", ""]
OUT.parent.mkdir(exist_ok=True)
OUT.write_text("\n".join(lines))
print(f"写入 {OUT}")
