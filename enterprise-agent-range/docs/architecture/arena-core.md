# Arena Core 架构

## 一句话

Arena Core 的职责是让红队成员面对一个可复用的企业 World 投毒和攻关，由真实或替身 Agent 自主调用工具，再由 SUT 裁决，最后由靶场根据副作用和审计判分。

## 当前双轨

| 轨道 | 用途 | 状态 |
|---|---|---|
| P0/P1 Replay | 旧 manifest + `execution.steps`，用于稳定回归和历史基线 | 保留 |
| Arena | `World + inject + task + oracle`，用于真实攻关平台 | 当前主线 |

## 核心流

```text
Finding/Challenge
  -> build World
  -> apply inject
  -> AgentSeat produces tool attempts
  -> SUTAdapter allow/deny/proxy
  -> World records side effects
  -> EvidenceStore captures transcript/audit/effects
  -> Oracle produces verdict
```

## 现有 office/mail 竖切

已跑通：

```text
OpenCode 1.17.12
  -> XA-Guard stdio MCP
  -> enterprise_agent_range.arena.mcp_office_server
  -> World(mailbox/project/egress)
```

结论：guard 模式拦截投毒预算外发；null 模式发生敏感外发；良性对照两边通过。

## 下一步架构拆分

`arena/live.py` 需要拆为通用部件：

- `opencode_seat.py`：OpenCode headless agent seat。
- `sut_xaguard.py`：外部 XA-Guard adapter 和临时 YAML 生成。
- `policy_overlay.py`：按 challenge/world 生成 Gate3/Gate4 临时配置。
- `evidence.py`：AttemptEvidence、EvidenceStore、hash manifest。
- `live_suite.py`：repeat、A/B、run manifest、报告入口。

保留 `arena/live.py` 作为兼容入口，减少 CLI 破坏。