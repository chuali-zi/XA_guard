# Auto-RedTeam · 本地 CLI 全自动智能体红队工作流

> ⚠️ **安全边界**：本工具只对**本仓库内的合成靶场 Open Agent Range（OAR）**发起攻击，用于测试团队自有防护 **XA-Guard**（挑战杯参赛作品）。纯合成 DCTG 世界数据、无真实凭据、无公网目标、无真实外发端点。遵守 [`../docs/redteam/REDTEAM-AGENT-TECHNICAL-MANUAL.md`](../docs/redteam/REDTEAM-AGENT-TECHNICAL-MANUAL.md) §14 全部安全规则。这是**授权的防御性红队研究**。

## 这是什么

一个**两层的全自动红队**：本地 **Conductor**（战役管理器）严格串行调用本地 **Cursor Agent CLI / OpenCode CLI / Codex CLI** 作为 proposal engine，对 OAR 持续、自适应地攻坚。模型只生成结构化 payload proposal；Conductor 负责 scope 校验、novelty 去重、跑 A/B（`null` 裸奔 vs `xaguard` 防御）、以 OAR ledger 判胜负、沉淀"七件套"证据、把有效 finding 标记为回归资产。

学术地基见 [`../../docs/references/literature/06_agent_redteam/`](../../docs/references/literature/06_agent_redteam/)。

## 文档地图

| 文档 | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | 两层架构、组件、数据流、时序图 |
| [docs/WORKFLOW.md](./docs/WORKFLOW.md) | campaign 生命周期状态机 + 持续模式 |
| [docs/ATTACK-CONTRACT.md](./docs/ATTACK-CONTRACT.md) | 本地三 CLI 的安全边界、串行规则与去重契约 |
| [docs/CURSOR-API-INTEGRATION.md](./docs/CURSOR-API-INTEGRATION.md) | 端点/鉴权/SSE 流/artifacts/配额/限流 |
| [docs/THREAT-MODEL.md](./docs/THREAT-MODEL.md) | 7 类攻击分类 → OAR 开放面映射（论文锚定） |
| [docs/EVIDENCE-CONTRACT.md](./docs/EVIDENCE-CONTRACT.md) | 本地 mission/A-B 证据 → 七件套 + git 锚定溯源落盘 |
| [docs/SAFETY-AND-BUDGET.md](./docs/SAFETY-AND-BUDGET.md) | 花费上限/合成数据/隔离分支/kill switch |

## 快速上手（零花费）

```bash
# 1. 依赖（首次；如无网见 memory: HTTPS_PROXY=http://127.0.0.1:7897）
pip install -e .                      # 父仓库；conductor 仅用标准库 + PyYAML

# 2. 离线自测（fake Cursor API + 本地 CLI 命令构造，不联网不花钱）
python -m pytest open-agent-range/auto-redteam/tests -q

# 3. Dry-run：打印目标队列、每个 agent 的种子提示、预算账本，不发真实请求
cd open-agent-range/auto-redteam
python -m conductor.conductor --dry-run --config conductor/config.example.yaml
```

## 真实运行（会产生本地 CLI/provider 花费，需显式开启）

```bash
cd open-agent-range/auto-redteam
python -m conductor.conductor --config conductor/my-config.yaml     # 受 config 里的 budget_usd / max_runs 约束
python -m conductor.conductor --stop                               # kill switch：停止下一安全点后的本地 campaign
```

默认 `engine: local`，`engines: [cursor_cli, opencode, codex]`。本机未安装 Cursor 独立 `agent` CLI 时，Conductor 会跳过 `cursor_cli` 并继续尝试 OpenCode/Codex；不会自动安装或修改用户环境。

## 目录

```
auto-redteam/
├── README.md            # 本文件
├── docs/                # 6 篇设计文档
├── conductor/           # 本地战役管理器（Python）
├── prompts/             # 云端 agent 种子/追加/晋级提示模板
├── schemas/             # campaign 配置 + finding 报告 JSON Schema
├── tests/               # 离线测试（fake cursor server）
└── .log/                # 模块工作日志
```
