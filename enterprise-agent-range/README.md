# Enterprise Agent Range

Enterprise Agent Range 是一个独立的企业级智能体安全靶场设计区，用于红队、漏洞验证、能力检测和证据化评测。

本目录与仓库中的 XA-Guard 产品代码严格解耦：

- 不导入 `src/xa_guard`。
- 不复用 XA-Guard 内部配置、策略、测试或运行时代码。
- 不修改既有 `docs/` 文档体系。
- 仅把 XA-Guard 或任何其他防护产品视为外部被测对象 `SUT`。
- 靶场自身的设计、状态、日志和后续实现都保留在 `enterprise-agent-range/` 内。

## 入口

- [文档索引](docs/00-index.md)
- [设计说明](docs/01-design-brief.md)
- [目标与范围](docs/02-goals-and-scope.md)
- [企业场景](docs/03-enterprise-scenario.md)
- [解耦契约](docs/04-decoupling-contract.md)
- [总体架构](docs/05-architecture.md)
- [数据模型](docs/15-data-model.md)
- [数据流设计](docs/16-data-flows.md)

## P0 运行

P0 已具备独立 Python runtime、P0 case manifest、synthetic fixtures、Null Adapter、oracle、metrics 和证据包输出。P1 已扩展到 242 个 case、66 个 mock tool、本地协议面和 HTML/compare 报告。所有运行时代码位于 `range_src/enterprise_agent_range/`，不导入 `src/xa_guard`。

```powershell
$env:PYTHONPATH = "range_src"
python -m enterprise_agent_range validate --manifest cases/p0_manifest.json
python -m enterprise_agent_range run --manifest cases/p0_manifest.json --out reports --run-id run-p0-null-verify --adapter null_adapter --sut-id null-baseline --mode local --operator codex
python -m unittest discover -s tests
```

最近一次本地 Null Adapter 验证输出在 `reports/run-p0-null-verify/`。Null Adapter 是无防护基线，attack case 失败代表基线会执行危险链路，不代表靶场 runtime 出错。

## P1 运行

```powershell
$env:PYTHONPATH = "range_src"
python -m enterprise_agent_range validate --manifest cases/p1_manifest.json
python -m enterprise_agent_range run --manifest cases/p1_manifest.json --out reports --run-id run-p1-null-verify --adapter null_adapter --sut-id null-baseline --mode local --operator codex
python -m enterprise_agent_range compare --baseline reports/run-p0-null-verify --candidate reports/run-p1-null-verify --out reports/compare-p0-p1-null
'{"id":1,"method":"tools/list"}' | python -m enterprise_agent_range serve-stdio
```

P1 输出在 `reports/run-p1-null-verify/`，包含 JSON/JSONL、Markdown、HTML 和 artifact hash；P0/P1 对比输出在 `reports/compare-p0-p1-null/`。

## 当前状态

当前已完成 P1 本地基线：P0 84 cases，P1 242 cases，44 个 fixture，66 个 MCP-like mock tool，JSON/JSONL/Markdown/HTML 证据包，本地 MCP-like stdio/HTTP 和 simulated IDE replay。尚未实现外部真实 SUT adapter、严格 MCP 兼容层、交互式前端可视化或容器编排。
