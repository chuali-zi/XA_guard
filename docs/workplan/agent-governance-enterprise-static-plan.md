# Agent Governance 企业静态实现工作计划

## 目标

把 Agent Governance v1 从 demo registry 升级为静态企业 IAM/RBAC/ABAC 参考实现。当前阶段只要求理论上符合企业化，并能通过本地单元测试、MCP envelope 集成测试和审计字段验证。

## 实施内容

- 新增 `schemas/governance-registry.schema.json`，固定 v0.2 registry 的对象和字段契约。
- 新增 `configs/governance.enterprise-static.yaml`，覆盖多租户、禁用主体/Agent、角色绑定、跨主体薪酬审批、预算和审批策略。
- 扩展 `src/xa_guard/governance.py`：
  - v0.1 demo registry 继续兼容。
  - v0.2 registry 支持 tenants、principals、groups、roles、role_bindings、agents、data_domains、approval_policies。
  - loader 做重复 ID、悬空引用、跨租户绑定、空 Agent allow-list、未知 permission action 校验。
  - 鉴权顺序固定为身份上下文、状态、租户隔离、Agent 分配、工具权限、数据域权限、资源主体范围、预算、审批策略。
- 扩展 MCP envelope：`principal_id` 作为 `human_principal` 的规范别名。
- 扩展 Gate6 审计：记录 registry_version、policy_version、decision_reason_code、role_ids、approval_policy_id。
- 更新静态前端样例，展示企业角色、审批策略和治理审计。

## 验收标准

- `configs/governance.demo.yaml` 原有测试不破坏。
- v0.2 企业样例可加载，能解释 Bob 越权、Alice 跨主体薪酬审批、禁用主体、跨租户访问、预算超限、工具权限拒绝。
- `_xa_guard` 不透传给下游工具。
- Capability token 原文不落审计。
- Gate6 审计包含稳定治理原因码和生效角色。

## 验证命令

```powershell
$env:PYTHONPATH='src;.'; python -m pytest tests/unit/test_governance.py tests/integration/test_governance_mcp.py tests/unit/test_config.py -q
$env:PYTHONPATH='src;.'; python -m pytest tests/unit/test_gate6_audit.py tests/unit/test_verify_audit_cli.py -q
$env:PYTHONPATH='src;.'; python -m pytest tests/unit/test_governance_enterprise.py -q
```

## 边界

本轮不接真实 SSO/LDAP/SCIM/JWT/HSM/审批后台/账单系统；所有企业身份、授权和审批策略均来自本地静态 registry。
