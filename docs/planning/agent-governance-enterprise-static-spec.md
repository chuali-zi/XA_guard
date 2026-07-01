# Agent Governance 企业静态规范

> 范围：本规范描述 XA-Guard 的静态企业身份化管理和鉴权模型。当前实现不接真实 SSO、LDAP、SCIM、JWT 验签、真实账单或真实审批后台；它用本地 registry 文件表达企业 IAM/RBAC/ABAC 语义，并在运行时做 fail-closed 预检和审计。

## 1. 对象模型

Registry v0.2 使用 `schema_version: xa-guard-governance/v0.2`，参考 schema 为 `schemas/governance-registry.schema.json`。

核心对象：

| 对象 | 说明 |
|---|---|
| `tenants` | 企业或组织租户边界。所有主体、角色、Agent、数据域和审批策略必须归属一个租户。 |
| `principals` | 静态人类身份上下文，字段包含 `principal_id`、`tenant_id`、`status`、`department`、`groups`、`attributes`、预算。 |
| `groups` | 企业组织组，用于把 principal 绑定到角色。 |
| `roles` | RBAC 角色，包含 `use_agent`、`call_tool`、`access_data_domain`、`cross_subject_access` 权限动作。 |
| `role_bindings` | 把 role 授予 principal 或 group。绑定不可跨租户。 |
| `agents` | Agent inventory，包含 owner、purpose、allowed_tools、allowed_data_domains、risk_level、max_autonomy、生命周期状态。 |
| `data_domains` | 数据域，包含 sensitivity、部门/角色访问约束、跨主体访问角色和审批要求。 |
| `budgets` | 主体级静态预算，运行时用于 `cost_estimate_usd` 门控；可覆盖 principal 内嵌预算。 |
| `approval_policies` | 静态审批策略，按敏感级别、跨主体访问、工具风险、Agent 自主级别触发 `require_approval` 或 `deny`。 |

## 2. 运行时入口

上游 MCP 工具参数可携带保留字段 `_xa_guard`：

```json
{
  "text": "summarize payroll row",
  "_xa_guard": {
    "tenant_id": "acme-corp",
    "principal_id": "alice.hr@acme.local",
    "agent_id": "hr-assistant",
    "data_domain": "payroll",
    "resource_owner": "bob.dev@acme.local",
    "task_id": "task-payroll-approve",
    "cost_estimate_usd": 0.3,
    "capability_token": {
      "scope": "payroll:read",
      "ttl": "5m",
      "token": "secret"
    }
  }
}
```

上游适配器会剥离 `_xa_guard`，业务下游工具只能看到业务参数。`principal_id`、`human_principal`、`principal`、`employee_id` 是兼容别名。

## 3. 鉴权顺序

启用 `governance.enabled=true` 后，治理预检在 Gate1 前执行，顺序固定：

1. Authentication context：缺 principal 或 agent 直接 deny。
2. Principal status：未知或非 active 主体 deny。
3. Agent status：未知或非 active Agent deny。
4. Tenant isolation：principal、agent、data domain 必须与请求租户一致。
5. Agent assignment：principal 通过显式 allow-list 或 RBAC `use_agent` 获得 Agent 使用权。
6. Tool permission：Agent inventory 允许工具，且 RBAC `call_tool` 允许该工具。
7. Data-domain permission：principal 通过直授、部门、角色或 RBAC `access_data_domain` 访问数据域。
8. Resource-owner scope：访问他人或 `all` 资源时，必须有跨主体角色或 RBAC `cross_subject_access`。
9. Budget：`cost_estimate_usd` 不得超过主体剩余额度。
10. Approval policy：敏感数据、跨主体访问、高自主 Agent 等触发 `REQUIRE_APPROVAL`。

任何校验失败都 fail closed，并写入 Gate6 审计。

## 4. 审计字段

Gate6 继续保留原有 `gen_ai.governance.*` 字段，并规范化：

| 字段 | 说明 |
|---|---|
| `gen_ai.governance.tenant_id` | 租户 |
| `gen_ai.governance.human_principal` | 人类主体 |
| `gen_ai.governance.agent_id` | Agent 身份 |
| `gen_ai.governance.data_domain` | 数据域 |
| `gen_ai.governance.resource_owner` | 被访问资源主体 |
| `gen_ai.governance.task_id` | 任务 ID |
| `gen_ai.governance.cost_estimate_usd` | 静态成本估算 |
| `gen_ai.governance.capability_token` | 能力令牌摘要；secret/token/signature 等只落 hash |
| `gen_ai.governance.registry_version` | registry 版本 |
| `gen_ai.governance.policy_version` | governance schema / policy 版本 |
| `gen_ai.governance.decision_reason_code` | 稳定 allow/deny/approval 原因码 |
| `gen_ai.governance.role_ids` | 本次判定生效角色 |
| `gen_ai.governance.approval_policy_id` | 命中的审批策略 |

## 5. 边界声明

- 不做真实登录态建立，不证明用户已通过企业 IdP 登录。
- 不做 LDAP/SCIM 同步，不承诺组织架构实时性。
- 不验签真实 JWT，不把 `_xa_guard` 当可信生产凭据。
- 不做真实账单，只做任务级成本估算和预算门控。
- 不做真实工单审批系统，只通过现有 MCP elicitation / pending approval 路径产生可审计审批闭环。
