# Enterprise Agent Range

Enterprise Agent Range 是一个独立的企业级智能体安全靶场，用于红队攻关、漏洞验证、能力检测和证据化评测。

本目录与仓库中的 XA-Guard 产品代码严格解耦：

- 不导入 `src/xa_guard`。
- 不复用 XA-Guard 内部配置、策略、测试或运行时代码。
- 不修改根 `docs/` 文档体系。
- 仅把 XA-Guard 或任何其他防护产品视为外部被测对象 `SUT`。
- 靶场自身的设计、状态、日志和后续实现都保留在 `enterprise-agent-range/` 内。

## 文档入口

当前文档已收束为红队靶场建设需要的活文档：

- [文档入口](docs/README.md)
- [红队靶场重构计划](docs/plan/redteam-arena-refactor-plan.md)
- [Arena Core 架构](docs/architecture/arena-core.md)
- [解耦契约](docs/architecture/decoupling-contract.md)
- [红队成员操作指南](docs/redteam/operator-guide.md)
- [Live office/mail smoke 结论](docs/reference/live-office-mail-smoke.md)

## P0/P1 回归运行

P0/P1 是旧的确定性回放基线，继续保留用于回归，不作为新增间接注入 case 的主线。

```powershell
$env:PYTHONPATH = "range_src"
python -m enterprise_agent_range validate --manifest cases/p1_manifest.json
python -m enterprise_agent_range run --manifest cases/p1_manifest.json --out reports --run-id run-p1-null-verify --adapter null_adapter --sut-id null-baseline --mode local --operator codex
python -m unittest discover -s tests
```

## Arena Live Smoke

`arena/` 是当前主线：World 与题库解耦，真实或替身 Agent 面对被投毒环境自主调用工具，SUT 负责裁决，靶场依据副作用和审计判分。

```powershell
$env:PYTHONPATH = "range_src"
python -m enterprise_agent_range arena-live --sut-mode both --repeat 1 --out reports --run-id arena-live-2x2-smoke --timeout-seconds 180
```

已知边界：当前 live 仍是 N=1 smoke，Gate3 overlay 仍需配置化，红队工作台尚未实现。