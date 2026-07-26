#!/usr/bin/env python3
"""Build a lightweight trend report from Paper-Notes Markdown files."""
from collections import Counter, defaultdict
from pathlib import Path
import re
import json
import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "data/Paper-Notes/docs")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "reports/paper-notes-trends.json")

def frontmatter(text):
    if not text.startswith("---"):
        return {}
    block = text.split("---", 2)[1]
    data = {}
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if m:
            data[m.group(1)] = m.group(2).strip().strip('"')
    return data

files = list(ROOT.glob("**/*.md"))
conference = Counter()
area = Counter()
keywords = Counter()
examples = defaultdict(list)

for path in files:
    rel = path.relative_to(ROOT)
    if len(rel.parts) < 2 or path.name == "search.md":
        continue
    conf, field = rel.parts[0], rel.parts[1]
    if path.name == "index.md":
        text = path.read_text(errors="ignore")
        for line in text.splitlines():
            if "高频主题" in line:
                for word, count in re.findall(r"([^：：·]+?)[×x](\d+)", line):
                    keywords[word.strip()] += int(count)
        continue
    if not re.fullmatch(r"(?:ACL|AAAI|CVPR|ECCV|ICCV|ICLR|ICML|NeurIPS)\d{4}", conf):
        continue
    conference[conf] += 1
    area[field] += 1
    text = path.read_text(errors="ignore")
    meta = frontmatter(text)
    title = meta.get("title", path.stem).replace("\\n", " ")
    # The generated index exposes a compact, useful signal in this line.
    for line in text.splitlines():
        if "高频主题" in line:
            for word, count in re.findall(r"([^：：·]+?)[×x](\d+)", line):
                keywords[word.strip()] += int(count)
    if len(examples[field]) < 3:
        examples[field].append(title)

report = {
    "source": str(ROOT),
    "markdown_files": len(files),
    "paper_files": sum(conference.values()),
    "conferences": conference.most_common(),
    "areas": area.most_common(),
    "high_frequency_topics": keywords.most_common(30),
    "examples": dict(examples),
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(f"写入 {OUT}: {report['paper_files']} 篇论文，{len(conference)} 个会议，{len(area)} 个领域")
print("会议:", report["conferences"])
print("领域 Top 15:", report["areas"][:15])
print("主题 Top 15:", report["high_frequency_topics"][:15])
