# PaperCompass

PaperCompass 是一个研究插件项目：它把本地论文笔记、趋势报告和实验产物转化为可审计的研究方向选择与研究问题细化流程。同一份插件同时支持 Codex CLI 与 Claude Code 两种运行时。

## 内容

- `plugins/hotspot-to-rq/`：**Hotspot to Research Question** 插件，支持从研究热点中发现方向，或评估已有实验应继续、修复、转向还是停止。双 manifest：`.codex-plugin/plugin.json`（Codex）与 `.claude-plugin/plugin.json`（Claude Code）。
- `.agents/plugins/marketplace.json`：仓库内的 Codex plugin marketplace 配置。
- `.claude-plugin/marketplace.json`：仓库内的 Claude Code plugin marketplace 配置。
- `scripts/`：同步上游 Paper-Notes、生成趋势报告与结构化热点数据的轻量脚本。

## 安装 Codex 插件

需要已安装并登录 Codex CLI。插件由此仓库现有的 marketplace（标识为
`personal`）提供；更新时保留该标识，避免破坏已有安装。

### 从 GitHub 安装

```bash
# 添加并固定到 main 分支的 marketplace
codex plugin marketplace add Endofthestars/PaperCompass --ref main

# 安装 Hotspot to Research Question 插件
codex plugin add hotspot-to-rq@personal
```

安装后，请新建一个 Codex 任务，再通过
`$hotspot-to-rq:research-direction-debate` 调用工作流。已打开的任务不会热加载
新安装或刚升级的 plugin 内容。

### 本地开发安装

仅在尚未配置名为 `personal` 的 marketplace 的新环境里，在本仓库根目录执行：

```bash
codex plugin marketplace add ./
codex plugin add hotspot-to-rq@personal
```

如果 `personal` 已指向 Git source，不要再执行 `marketplace add ./`；修改 plugin
后先更新开发 cachebuster，再运行下方测试。Git marketplace 需要提交并推送新
版本后才能刷新：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py" \
  plugins/hotspot-to-rq
./scripts/test_plugin.sh

codex plugin marketplace upgrade personal
codex plugin add hotspot-to-rq@personal
```

刷新后新建 Codex 任务验证新版本。

## 安装 Claude Code 插件

需要已安装并登录 Claude Code（v2.x 及以上）。marketplace 标识同样是
`personal`，与 Codex 侧保持一致。

### 从 GitHub 安装

在 Claude Code 会话中执行：

```text
/plugin marketplace add Endofthestars/PaperCompass
/plugin install hotspot-to-rq@personal
```

### 本地开发安装

在本仓库根目录打开 Claude Code，然后执行：

```text
/plugin marketplace add ./
/plugin install hotspot-to-rq@personal
```

安装后技能会注册为 `/hotspot-to-rq:research-direction-debate`。修改 plugin
后运行 `/plugin marketplace update personal` 刷新，再新开会话验证。注意：
已安装的插件从 `~/.claude/plugins/cache/` 里的副本运行——skills、hooks、
agents 与 workflows（按 `hotspot-to-rq:dispatch-batch` 名称解析）都不会
读取仓库工作区；直接改仓库源码对当前会话不生效，必须刷新 marketplace
并重开会话。

两个已实测的开发循环陷阱（BUGS.md P-02/P-03）：版本号不变的改动会被
`claude plugin update` 短路——提示 already at the latest version 而缓存里
仍是旧字节，必须升版本号或 `uninstall` + `install` 才真正生效；
`installed_plugins.json` 记录的 `gitCommitSha` 只是安装时刻的 HEAD，从脏
工作树安装时它不能代表实际运行的字节，正式发布请从干净提交安装并打 tag。

### 调用方式

```text
/hotspot-to-rq:research-direction-debate
/hotspot-to-rq:research-direction-debate evaluate 我的现有实验方向……
```

也可以直接用自然语言描述研究方向选择/实验评估需求，Claude 会按技能描述
自动路由；斜杠命令后的参数会作为模式与主题种子直接进入路由。两种运行时
共享同一份 SKILL.md、references、校验脚本与 vendored ARS 角色提示；
`.codex-plugin/` 与 `.claude-plugin/` 只是各自运行时的 manifest 入口，
版本号基线保持一致（Codex 侧附加 `+codex.<timestamp>` cachebuster）。

在 Claude Code 下插件还带一层机制强制：每次写入
`reports/research-direction/<session-id>/session-state.json` 后，插件的
PostToolUse hook 会自动运行 `validate_session.py`，校验失败会立刻反馈给
模型（协议的 fail-closed 不再依赖模型自觉）。三个捆绑 agent
（`mainline-controller`、`research-role`、`search-verification`）以工具
白名单和 `maxTurns` 上限机制化执行角色隔离契约。

插件还带一个 `dispatch-batch` workflow（需 Claude Code v2.1.154+，注册为
`/hotspot-to-rq:dispatch-batch`），供编排者把 controller 已提交的一个调度
批次（批内角色互相独立）交给确定性脚本并行执行：每个 dispatch 得到干净
上下文、按角色契约强制的结构化输出和 envelope 回显预检。它刻意不做整轮
编排——轮内依赖角色必须逐层经过 controller 的 ROLE_BOUNDARY 检查点，这是
schema 1.4 控制契约的要求。envelope 校验、状态落盘与校验器执行仍由编排
者完成。

Codex 侧的机制强制现状：上游 Codex plugin ingestion 契约不接受 `hooks`、
agents、workflows 等 manifest 字段（validator 直接拒绝未知字段），因此不把
Claude 专属字段写入 Codex manifest。Codex 改由技能协议通过通用子任务复现相同的
controller/角色顺序与独立批处理，但通用子任务继承运行时工具，这些角色边界属于模型级
约束，不等同于 Claude 的 per-agent 工具白名单。Codex 长上下文由主任务保留完整项目
证据；每个非 CONTROL 角色只接收一个不可变 evidence capsule 的绝对路径，原始文件
不会进入子任务 allowlist。确定性 builder 在 controller transition 提交前固化最终
envelope、SHA-256、预算和 transport packet，并对指令、inline payload、胶囊与传输
预留实施完整 UTF-8 字节上限，而不是把字符数误当 token 数；初次调度及重试都读取相同
的持久化字节，并先通过不可变 batch manifest 复核 packet 与 capsule 摘要。
调度时还会核对对应 CONTROL transition 已存在于当前合法 session，并直接使用
校验器输出的原始 packet 字节，避免“校验后重新读取”的竞态窗口。
两侧继续执行同一套 envelope、状态和 validator 规则。Codex
运行时的 hooks 特性已稳定，会自动发现插件根目录的 `hooks/hooks.json`
（无需 manifest 字段），并为插件 hook 注入 `CLAUDE_PLUGIN_ROOT` 兼容
变量——用户在信任审查（trust review）通过后即获得与 Claude 侧相同的
session-state 写后校验。hook 脚本同时解析三种写入形态：Write/Edit 的
`file_path`、Codex `apply_patch` 的补丁文本、以及 Bash 命令文本中的
session-state 路径（后者也堵住了 Claude 侧经 shell 重定向绕过 hook 的
旁路）。该行为已按 Codex 官方 hook 事件 schema 适配，尚未在真机安装中
端到端验证。无 hook 可用时，SKILL.md 仍要求编排者在每次写入
`session-state.json` 后立即自行运行 `validate_session.py` 兜底。Codex
manifest 侧的对等优化：与 Claude manifest 一致的 `keywords`、
`homepage`/`repository` 元数据，`defaultPrompt` 为规范要求的数组形式
（≤3 条、每条 ≤128 字符）；skill 级 `agents/openai.yaml` 显式钉住
`policy.allow_implicit_invocation: true`。单元测试把上游 ingestion 契约
的字段白名单编码进本地 CI，防止 Claude-only 字段误入 Codex manifest。

## Plugin 工作流

```text
主代理识别 DISCOVER / REFINE / RQ-only / EVALUATE
  → 创建 schema 1.4 session，并将 transport_profile 固定为 CLAUDE 或 CODEX
  → Mainline Workflow Controller 检查状态并批量调度独立角色
  → 主代理执行调用、写入产物
  → Panel Judge 给出科学判断
  → Controller 在角色/轮次/阶段边界决定推进、修复、重试、暂停或阻塞
  → deterministic validator 放行 user gate
  → 主代理获取并记录用户 receipt
  → RQ 确认后完成；EVALUATE 则在实验决策后生成最小下一实验计划并校验完成
```

Mainline Workflow Controller 是只读控制面，不是第二个主代理：它不能搜索、
改文件、替 Panel Judge 判断研究价值，或替用户选择。主代理仍是唯一执行者和
用户接口。

## 实际测试 Plugin

静态验证和回归测试：

```bash
./scripts/test_plugin.sh
```

该脚本会运行单元测试与 Codex 校验器；当本机安装了 Claude Code CLI 时，
还会对 Claude 侧 manifest 与 marketplace 运行 `claude plugin validate
--strict`（Codex manifest 由 Codex 校验器与 JSON 语法检查覆盖）。

端到端 smoke test：

1. 按“本地开发安装”安装或刷新 plugin；用 `codex plugin list --json` 确认
   `hotspot-to-rq` 的已安装版本与
   `plugins/hotspot-to-rq/.codex-plugin/plugin.json` 完全一致，再新建 Codex
   任务。旧任务不会热加载新版本。
2. 调用：

   ```text
   Use $hotspot-to-rq:research-direction-debate with its Mainline Workflow
   Controller to inspect this project and stop at the first required user gate.
   ```

3. 确认首次输出会报告路由、session、controller 状态和当前阶段，而不是直接
   给出最终研究方向。
4. 检查 `reports/research-direction/<session-id>/session-state.json`：
   `schema_version` 为 `1.4`、`transport_profile` 为 `CODEX`，
   `mainline_control.revision` 连续递增，
   CONTROL packet 与 transition 一一对应；每个 transition 的
   `control_input_path` 都存在且 digest 匹配。
5. 在方向 gate 回复选择后，确认存在对应 `gate_receipts`，且不会重复 dispatch
   已接受或已拒绝的 packet。RQ `CONFIRM` receipt 必须同时绑定候选 ID 和用户
   实际看到的 RQ packet ID；确认后只能执行确认落盘与完成校验，不能再改写 RQ。
6. 对 session 运行：

   ```bash
   python3 -B <skill-root>/scripts/validate_controller_decision.py \
     reports/research-direction/<session-id>/session-state.json \
     <controller-output.json> \
     --control-input reports/research-direction/<session-id>/control-input.json

   python3 -B <skill-root>/scripts/validate_session.py \
     reports/research-direction/<session-id>
   ```

   第一条用于每次 controller 调用落盘前；第二条用于每个 staged
   transition。只有两者都通过后，工作流才应执行 dispatch、展示 user gate
   或声明完成。

## 数据工作流

```text
同步上游论文笔记 → 生成趋势信号 → 运行插件的方向选择 / 实验评估工作流
```

论文笔记数据来自 [`zhaoyang97/Paper-Notes`](https://github.com/zhaoyang97/Paper-Notes)。`data/Paper-Notes/docs` 是由 GitHub Actions 镜像并纳入版本控制的语料；其中的 `LICENSE` 与 `UPSTREAM.md` 保留其许可证、来源 revision 和同步时间。请遵守其 CC BY-NC-SA 4.0 许可，并在报告中注明来源与同步时间。

```bash
./scripts/sync_paper_notes.sh
python3 scripts/analyze_paper_notes.py
python3 scripts/build_trend_report.py
```

默认会将上游 `docs/` 语料同步到 `data/Paper-Notes`，将分析结果输出至 `reports/`；只有后者由 Git 忽略。上游当前约 382 MB，随每周更新会增加仓库历史体积。

GitHub Actions 的 **Sync Paper-Notes Corpus** 工作流会在每周一 `07:17 UTC`
自动运行。也可以在仓库的 **Actions** 页面选择该工作流、点击 **Run workflow**
手动同步；只有上游 `docs/` 或许可证版本改变时，机器人才会提交到 `main`。
