# policy 模块工作日志

---

## 2026-06-17 Codex 主 agent - OPA/Rego merged-view 原型

- 新增 `opa_export.py` 和 `scripts/export_opa_policy.py`，可导出 `LayeredPolicySource` 当前生效视图为 OPA `data.json`、`gate3.rego` 和 `manifest.json`。
- `LayeredPolicySource` 新增 `get_sensitive_patterns()`，并在 snapshot 内保留合并后的敏感词列表，供 data export 使用。
- `Gate3Policy backend=rego + prefer_layered=true` 支持按 `bundle_sha` 缓存 merged rules 的 `RegoPolicyEngine`；无 OPA binary 时仍走 Python fallback。
- 验证：`test_opa_export.py`、layered policy 测试、Gate3 merged-view Rego 测试通过；CLI export smoke 通过。

---

## 2026-06-04 layered.py risk_level 单一事实源

**改动**：在 `layered.py` 新增 `_derive_tool_risks_from_caps()` 辅助函数，在 `_compile_layer` 中当无独立 risks_path（baseline 层）时，从 caps 的 risk_level 字段自动派生 tool_risks 映射；overlay 层若同时提供 tool_risks.yaml 则保留（用于单调性检验），并补全 caps 中未覆盖的工具。

**manifest 变更**：移除 `tool_risks:` 资源条目，baseline 不再加载 gate2_tool_risks.yaml，risk_level 来源唯一化至 gate4_capabilities.yaml。

**gate2_plan.py 改动**：
1. fail-open 默认从 GREEN 改为 YELLOW（可配置 default_risk 选项）；
2. 增加单一事实源注释；
3. 新增 test_unknown_tool_green_when_configured 测试验证向后兼容。

**测试**：94 passed，全绿。

---

## 2026-05-25 agent-G3
- loader.py / compiler.py 无需改动；签名稳定
- 验证：load_policy_yaml 对 10 条 seed 规则全部解析通过；compile_predicate 在 builtins=None 沙箱内执行 risk/taint/role/sources/contains() 表达式正常
- 修正 policies/enterprise-l3.yaml：GBT-22239-8.1.3.1 / 8.1.4.2 两条规则的 triggers 与 predicate 引用工具不一致（triggers 是抽象动作名，predicate 是具体工具名），统一扩展 triggers 列表使其与 predicate 中 tool in (...) 同步
- 已知问题：predicate 表达式语法未做白名单过滤；M3 切 OPA 后由 Rego 语义约束接管
- 后续 TODO：predicate AST 校验（禁止 dunder / import 风险）；rego backend 在 M3 接 OPA HTTP/embedded

---

## 2026-05-24 23:55 主助手
- loader.py / compiler.py 接口骨架
- 决策（implementation-notes Q9）：demo 用 Python predicate（受限 eval, builtins=None）；M3 切 OPA Rego
- 决策：predicate 表达式可用变量 tool/args/role/taint/risk/sources + contains() 辅助
- TODO（agent-G3）：扩 predicate 表达式安全检查；非法字符抛错；接 OPA 时保持 backend 字段切换
