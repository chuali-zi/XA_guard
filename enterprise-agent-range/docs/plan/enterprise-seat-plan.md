# 企业级 Agent Seat 规划（模拟）

> 范围：`enterprise-agent-range/` 独立靶场。
> 目的：为模拟企业"数字城市科技集团"设计 Agent Seat 体系，涵盖席位分级、域分配、权限边界、成本模型与治理约束。
> 本文件是设计规划，不修改 runtime 代码。

## 1. 模拟企业概况

| 属性 | 值 |
|---|---|
| 企业名 | 数字城市科技集团（Digital City Tech Group） |
| 员工规模 | ~500 人（模拟） |
| Agent 渗透率 | 目标 30%（~150 个活跃 Agent Seat） |
| 主要域 | Office、Operations、Business Data、Dev Supply、Governance、Audit |
| 数据分级 | PUBLIC、INTERNAL、CONFIDENTIAL、SECRET（仅不可用样本） |

## 2. Agent Seat 定义

一个 **Agent Seat** 代表一个企业级 Agent 实例的完整配置单元，包含：

```
Seat = {
  identity:    谁在使用（员工 / 部门 / 系统角色）
  capability:  能调用哪些工具、访问哪些数据域
  policy:      受哪些 Gate3/Gate4 规则约束
  cost:        每次调用的预算归属与上限
  audit:       操作可追踪至 Seat + 员工
  lifecycle:   创建 → 分配 → 活跃 → 冻结 → 销毁
}
```

当前 `opencode_seat.py` 实现的 `OpenCode agent seat` 是 Arena 测试用的单 seat 实例；本规划将其扩展到多个域、多个角色、多级权限的企业场景。

## 3. Seat 分级

| 级别 | 代号 | 模型 | 并发 | 预算权重 | 典型使用者 | 说明 |
|---|---|---|---|---|---|---|
| L1 标准 | `standard` | glm-5.2 / gpt-4o-mini | 1 | 1x | 普通员工 | 日常办公、邮件、查询 |
| L2 增强 | `power` | gpt-5.5 / claude-4.5 | 2 | 3x | 技术主管、项目经理 | 业务数据分析、审批建议 |
| L3 审计 | `audit` | gpt-5.5 (xhigh) | 1 | 4x | 合规、安全团队 | 审计回放、证据重算 |
| L4 特权 | `privileged` | gpt-5.5 (xhigh) | 1 | 5x | 系统管理员、安全官 | 高危操作、策略变更 |
| X 测试 | `test` | 任意 | 1 | 0.1x | 红队、开发 | 靶场测试、回归验证 |

## 4. 按域 Seat 分配

| 域 | 标准(L1) | 增强(L2) | 审计(L3) | 特权(L4) | 合计 |
|---|---|---|---|---|---|
| Office（办公） | 40 | 10 | 2 | 0 | 52 |
| Operations（运维） | 15 | 8 | 2 | 3 | 28 |
| Business Data（业务数据） | 25 | 12 | 3 | 1 | 41 |
| Dev Supply（研发供应链） | 10 | 5 | 1 | 1 | 17 |
| Governance（治理） | 5 | 3 | 2 | 1 | 11 |
| Audit（审计） | 1 | 2 | 4 | 0 | 7 |
| **合计** | **96** | **40** | **14** | **6** | **156** |

### 4.1 Office 域 Seat

| Seat 名称 | 级别 | 角色 | 工具访问 | 数据域 | 说明 |
|---|---|---|---|---|---|
| `office.default.N` | L1 | 员工 | read_mail, send_email | INTERNAL 邮件 | 日常办公 |
| `office.manager.N` | L2 | 部门主管 | read_mail, send_email, query_project | INTERNAL + 预算 | 含跨域项目查询 |
| `office.audit.N` | L3 | 合规专员 | read_mail（只读）, query_project（只读） | 全域只读 | 监督审计用 |

### 4.2 Operations 域 Seat

| Seat 名称 | 级别 | 角色 | 工具访问 | 数据域 | 说明 |
|---|---|---|---|---|---|
| `ops.default.N` | L1 | 运维工程师 | exec_command（受限）, read_log | INTERNAL | 常规运维 |
| `ops.power.N` | L2 | 高级运维 | exec_command, read_log, restart_service | INTERNAL + CONFIDENTIAL | 变更执行 |
| `ops.audit.N` | L3 | 安全运维 | read_log（只读）, read_config（只读） | 全域只读 | 安全监控 |
| `ops.admin.N` | L4 | 系统管理员 | exec_command（无限制）, write_config | SECRET 除外 | 最高运维权限 |

### 4.3 Business Data 域 Seat

| Seat 名称 | 级别 | 角色 | 工具访问 | 数据域 | 说明 |
|---|---|---|---|---|---|
| `biz.default.N` | L1 | 业务员 | query_record, submit_ticket | INTERNAL | 日常业务 |
| `biz.power.N` | L2 | 业务主管 | query_record, query_report, submit_ticket, approve | CONFIDENTIAL | 含审批和报表 |
| `biz.audit.N` | L3 | 数据审计 | query_record（只读）, query_report（只读） | 全域只读 | 数据合规检查 |
| `biz.admin.N` | L4 | 业务系统管理员 | query_all, modify_schema | SECRET 除外 | 业务系统配置 |

### 4.4 Dev Supply 域 Seat

| Seat 名称 | 级别 | 角色 | 工具访问 | 数据域 | 说明 |
|---|---|---|---|---|---|
| `dev.default.N` | L1 | 开发者 | read_repo, query_aibom | PUBLIC + INTERNAL | 日常开发 |
| `dev.power.N` | L2 | 高级开发 | read_repo, query_aibom, publish_plugin | INTERNAL | 含发布权限 |
| `dev.audit.N` | L3 | 供应链审计 | query_aibom（只读）, query_dependency | 全域只读 | SBOM 审核 |
| `dev.admin.N` | L4 | 仓库管理员 | write_repo, manage_ci, override_aibom | SECRET 除外 | CI/CD 管理 |

### 4.5 Governance 域 Seat

| Seat 名称 | 级别 | 角色 | 工具访问 | 数据域 | 说明 |
|---|---|---|---|---|---|
| `gov.default.N` | L1 | 治理专员 | query_policy, query_registry | INTERNAL | 政策查询 |
| `gov.power.N` | L2 | 治理主管 | query_policy, update_registry | CONFIDENTIAL | 注册表维护 |
| `gov.audit.N` | L3 | 治理审计 | query_policy（只读）, query_registry（只读） | 全域只读 | 治理检查 |
| `gov.admin.N` | L4 | 安全官 | modify_policy, override_deny | SECRET 除外 | 策略终极权限 |

### 4.6 Audit 域 Seat

| Seat 名称 | 级别 | 角色 | 工具访问 | 数据域 | 说明 |
|---|---|---|---|---|---|
| `audit.default.N` | L1 | 审计助理 | query_audit_log（受限） | INTERNAL | 常规日志查询 |
| `audit.power.N` | L2 | 审计师 | query_audit_log, verify_chain, replay_trace | CONFIDENTIAL | 审计线索追踪 |
| `audit.expert.N` | L3 | 高级审计师 | query_audit_log, verify_chain, replay_trace, export_evidence | 全域只读 | 取证导出 |

## 5. Seat 权限矩阵

### 5.1 跨域访问规则

| 源域 → 目标域 | PUBLIC | INTERNAL | CONFIDENTIAL | SECRET |
|---|---|---|---|---|
| Office | 允许 | 允许 | 仅 L2+ | 拒绝 |
| Operations | 允许 | 允许 | 允许 L2+ | 拒绝 |
| Business Data | 允许 | 允许 | 允许 L2+ | 拒绝 |
| Dev Supply | 允许 | 允许 | 拒绝 | 拒绝 |
| Governance | 允许 | 允许 | 允许 L2+ | 拒绝 |
| Audit | 允许 | 允许 | 允许 | 仅 L3 不可用样本 |

### 5.2 Seat 级默认 deny

所有 Seat 默认 deny 以下操作：
- 写 SECRET 数据域
- 向 external sink（公网邮件 / HTTP）发送 CONFIDENTIAL+
- 修改非本 Seat 域的审计日志
- 绕过 Gate3 规则（如发工资条到个人邮箱）
- 提升另一 Seat 的权限级别
- 删除审计记录

## 6. 委托链约束

当跨域或跨 Seat 委托时：

| 场景 | 约束 | 审计字段 |
|---|---|---|
| L1 委托 L2 查预算 | 需 L2 显式 approve | `delegation_chain.0.principal` |
| L3 审计查询跨域 | 自动允许只读 | `delegation_chain.0.principal` |
| L4 策略变更 | 必须 MFA + 审计审批 | `delegation_chain.0.principal` + `approval_ticket` |
| 测试 Seat 访问生产数据 | 拒绝（fail-closed） | `delegation_chain.deny_reason` |

委托链格式与现有 `Challenge.delegation_chain` 兼容：
```json
[
  {"principal": "alice@dctg.local", "role": "L1"},
  {"principal": "bob@dctg.local", "role": "L2", "approval_ticket": "APPR-20260701-003"}
]
```

## 7. Seat 生命周期

```
Provisioning → Active → Suspended → Retired
     |            |          |
     v            v          v
 创建 Seat   正常使用    临时冻结
 分配角色   工具调用     保留审计
 绑定预算   审计记录     不可调用
```

### 7.1 关键事件

| 事件 | 触发 | 动作 |
|---|---|---|
| Seat 创建 | HR 入职 / 部门新建 | 分配 ID、级别、默认 policy |
| Seat 升级 | 岗位变动 | 提升级别，保留审计连续性 |
| Seat 冻结 | 员工休假 / 调查 | 保留 seat 但 deny 所有 tool call |
| Seat 销毁 | 离职 / 系统下线 | 保留审计日志 180 天，删除 token |
| Seat 被攻陷 | 红队 / SOC 检测 | 立即冻结，触发全域审计追溯 |

## 8. 成本模型

### 8.1 单 Seat 估算成本

| 级别 | 模型 | 月均调用 | 单次均成本 | 月均 Seat 成本 |
|---|---|---|---|---|
| L1 | glm-5.2 / gpt-4o-mini | 500 | $0.01 | $5 |
| L2 | gpt-5.5 / claude-4.5 | 300 | $0.03 | $9 |
| L3 | gpt-5.5 (xhigh) | 100 | $0.10 | $10 |
| L4 | gpt-5.5 (xhigh) | 50 | $0.20 | $10 |

### 8.2 企业月均总成本

| 级别 | Seat 数 | 月均总成本 |
|---|---|---|
| L1 | 96 | $480 |
| L2 | 40 | $360 |
| L3 | 14 | $140 |
| L4 | 6 | $60 |
| **合计** | **156** | **$1,040** |

注：此为企业模拟预算，与比赛 `subscription_budget60_v1`（`$60` 总 cap）相互独立。

## 9. 与 Arena Core 的关系

| Arena Core 组件 | Seat 规划映射 |
|---|---|
| `opencode_seat.py` | 当前只实现 1 个 Live Victim Seat，未来应支持多 Seat 规格 |
| `WorldSpec` | 每个 World 应声明本 World 内可用的 Seat 角色列表 |
| `Challenge` | Challenge 可指定 target_seat_level（如 `["L1", "L2"]`） |
| `PolicyOverlay` | 按 Seat level 生成对应的 Gate3/Gate4 策略覆盖 |
| `SUTAdapter` | XA-Guard 侧应接收 Seat identity 作为 `_xa_guard` envelope 字段 |
| `EvidenceStore` | Evidence 路径应包含 Seat identity |

### 9.1 Arena 测试中的 Seat 用法

当前 Arena live 使用单 seat `ear-live-victim`（L1 等效），未来可扩展为：

```text
Red-team 构造攻击 → Challenge.target_seat_level = "L2"
  → Arena 分配 L2 Seat（biz.power.1）
  → OpenCode 以 L2 身份运行
  → XA-Guard 收到 _xa_guard.principal = "biz.power.1@dctg.local"
  → Gate3 按 L2 规则放行更广泛的数据
  → Oracle 检验是否越权
```

## 10. 安全边界

1. 本规划中的 SECRET 数据域仅存在于 schema 定义和审计日志，不在任何真实 agent 工具入参中出现。
2. L4 seat 的 `modify_policy` 操作必须有独立的 MFA 审批记录。
3. Seat 身份不可被非本 seat 的 agent 伪造或继承（`original_principal` 审计字段阻止身份冒用）。
4. Arena 测试时，test seat 不可混入生产统计口径。
5. 成本模型为模拟估算，与真实 provider 账单和比赛预算无关。

## 11. 下一步

1. 审核本规划中的 Seat 分级和域分配是否合理。
2. 确认是否将 Seat level 写入 Challenge schema 作为可选字段。
3. 评估是否扩展 `opencode_seat.py` 以支持多 Seat 规格（非当前 Arena Core 阶段目标）。
4. 后续 Arena Core 稳定后，按本规划在 `arena run-ab` 中支持 `--seat-level` 参数。
