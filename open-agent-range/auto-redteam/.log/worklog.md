# auto-redteam 工作日志

## 2026-07-10 · 本地三 CLI 串行后端
将默认后端从 Cursor Cloud 改为 local proposal-only：Cursor Agent CLI / OpenCode / Codex 严格串行，新增 `engines.py`、`scope.py`、`novelty.py`、proposal schema/prompt 与安全契约。Conductor 统一执行 A/B 与证据封存。已通过离线测试和 compileall；未跑真实付费 campaign，Cursor `agent` 当前缺失。

## 2026-07-09 · 初版搭建
建 `feat/cursor-auto-redteam` 分支。设计并落地"全自动 Cursor 云端红队工作流"：两层架构——本地 Conductor（战役管理器，纯 Python 无 LLM）经 Cursor Cloud Agents REST API 起云端 agent 当红队大脑，对 Open Agent Range 持续、自适应攻坚。

产出：
- 文献：`docs/references/literature/06_agent_redteam/` 8 篇笔记（攻击面分类/自适应/PISmith/ChatInject/自动化评估/多agent/MetaSecAlign）+ README，更新 INDEX。
- 设计文档：`docs/` 6 篇（ARCHITECTURE / WORKFLOW / CURSOR-API-INTEGRATION / THREAT-MODEL / EVIDENCE-CONTRACT / SAFETY-AND-BUDGET）+ README。
- 引擎：`conductor/`（cursor_client / objectives / evaluator / evidence_sync / promote / conductor 主循环）+ config 示例；`prompts/` 3 模板；`schemas/` 2 个。

关键决策：胜负只读 OAR ledger（summary.json 的 asr_null/asr_guard/violations），绝不 LLM 自评；受限自治（agent 只写 findings 分支+建 PR，不推 main）；三重预算护栏 + kill switch；证据走七件套→标准 run 目录→git 锚定 provenance。

下一步：离线测试（fake cursor server）+ dry-run 验证。真实 run 需付费 key，默认不跑。
