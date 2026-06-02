# 企业 overlay 策略层（L1 / 动态扩展层）

每个企业接入时在本目录新建一个子目录：

```
policies/overlay/<tenant_id>/
├── manifest.yaml          # 声明本租户的命名空间
├── tool_risks.yaml        # 只能 ADD 新工具，或把现有工具风险等级 ↑（不能 ↓）
├── policy.yaml            # 只能 ADD 新规则；rule.id 必须以 tenant::<tenant_id>:: 开头
├── tool_capabilities.yaml # 只能 ↓ input_max_taint（更收紧）；可 ADD 新工具
└── sensitive_patterns.yaml# 任意 ADD（永不删除 baseline）
```

## 不可逾越的红线

`src/xa_guard/policy/monotonicity.py` 启动时强制校验，违例则整批 overlay 拒绝加载，
保留旧版本，写一条 audit 告警。具体红线：

1. `rule.id` 命中 baseline → 拒绝整批 overlay（不允许覆盖国标规则）
2. `tool_risks` 同名工具等级从 `red → green` / `yellow → green` → 拒绝
3. `tool_capabilities` 同名工具的 `input_max_taint` 放宽（如 `PUBLIC → CONFIDENTIAL`）→ 拒绝
4. `sensitive_patterns` 删除 baseline 正则 → 拒绝（增加无限制）

参考：
- AWS SCP（Deny 不被 IAM Allow 推翻）
- Google Model Armor Floor Settings（模板不得低于阈值）
- Kubernetes Gatekeeper ConstraintTemplate（逻辑写死，租户只填参数）

详见 `docs/产品架构.md` §3.3 关卡 3 / 关卡 4。
