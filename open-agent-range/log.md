# 工作日志

## 2026-07-04 SP0 真实沙盘适配性检查

- 对照 `PRD.md`、`status.md`、`docs/specs/SP0-walking-skeleton-design.md` 和 `spike.py` 检查当前 spike 是否符合“真实一天沙盘，而不是复杂题目”的预期。
- 本地重跑 `python spike.py`、`python spike.py --probe-violation` 和 AST 语法检查，均通过；本次未重跑 OpenCode live 模型调用。
- 结论：当前 spike 符合 SP0 walking skeleton，证明世界、工具、账本、属性判据和 Seat adapter 闭环成立；但仍不是可交给红队的真实沙盘，复杂度不足，缺多流程世界状态、开放注入面、SUT in-loop、持久化账本和追责/报告层。

## 2026-07-04 SP0 walking skeleton 验收补记

- 修复了 Windows 控制台中文输出编码问题，`spike.py` 入口会将 stdout/stderr 重配为 UTF-8。
- 修复了 Python 子进程调用 OpenCode 时找不到/误用 npm shim 的问题，OpenCode adapter 现在优先解析 `opencode.cmd`。
- 调整 OpenCode prompt：放弃容易触发项目读取/总结行为的大 JSON prompt，改成严格的一行 action JSON schema prompt；默认 OpenCode agent 使用 `build`。
- 已完成验收：`python spike.py`、`python spike.py --probe-violation`、`python spike.py --agent opencode --model deepseek/deepseek-v4-flash` 均通过。
- 已完成不写 `.pyc` 的 AST 语法检查；清理了本次验证产生的 `__pycache__` 和 `.runtime` 临时目录。
- 仍未完成：这还不是正式 SP1 内核；OpenCode Seat 仍是一轮 action plan，不是多轮 tool loop；XA-Guard/SUT、持久化账本、通用注入面、红队工作台都还没接入。
## 2026-07-04 SP0 walking skeleton spike

- 读取了 `PRD.md`、`docs/README.md` 和 `.log/worklog.md`，确认项目目标是开放企业级智能体红队靶场平台，核心约束是内核通用、场景当数据、不脚本化攻击、判据从账本事实读取。
- 确认本机存在 `opencode 1.17.12`，并通过 `opencode models deepseek` 查到可用模型名包括 `deepseek/deepseek-v4-flash`。
- 新增 `docs/specs/SP0-walking-skeleton-design.md`，描述本次 spike 的目标、边界、模型、验收和后续拆分方向。
- 新增 `spike.py`，实现一个最小模拟世界：企业记录、外部接收方、正常背景流、hash-chain 账本、工具表面、scripted Seat、OpenCode Seat adapter、敏感数据外发属性判据。
- 新增 `status.md`，记录当前仓库状态、已具备能力、距离 PRD 的缺口和下一步。
- 尚未完成：还未在本日志条目写入时完成验收命令运行；OpenCode Seat 仍是一轮 JSON action plan，不是正式多轮 tool loop；还没有 XA-Guard/SUT in-the-loop、持久化账本、通用注入面或红队工作台。
