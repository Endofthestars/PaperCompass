# PaperCompass

PaperCompass 是一个 Codex 插件项目：它把本地论文笔记、趋势报告和实验产物转化为可审计的研究方向选择与研究问题细化流程。

## 内容

- `plugins/hotspot-to-rq/`：**Hotspot to Research Question** 插件，支持从研究热点中发现方向，或评估已有实验应继续、修复、转向还是停止。
- `.agents/plugins/marketplace.json`：仓库内的 Codex plugin marketplace 配置。
- `scripts/`：同步上游 Paper-Notes、生成趋势报告与结构化热点数据的轻量脚本。

## 数据工作流

```text
同步上游论文笔记 → 生成趋势信号 → 运行插件的方向选择 / 实验评估工作流
```

论文笔记数据来自 [`zhaoyang97/Paper-Notes`](https://github.com/zhaoyang97/Paper-Notes)，并以本地数据目录方式使用，不随本仓库提交。请遵守其 CC BY-NC-SA 4.0 许可，并在报告中注明来源与同步时间。

```bash
./scripts/sync_paper_notes.sh
python3 scripts/analyze_paper_notes.py
python3 scripts/build_trend_report.py
```

默认会将上游仓库存放在 `data/Paper-Notes`，将分析结果输出至 `reports/`；两者都由 Git 忽略。
