"""演示资源：靶子 MCP server + 攻击场景脚本。

# 3 个演示场景

| 场景 | 文件 | 攻击类型 | 期望关卡 |
|------|------|----------|----------|
| 01 | demo/scenarios/scenario_01_indirect_injection.py | 间接提示注入 | 关卡 1 + 关卡 3 → DENY |
| 02 | demo/scenarios/scenario_02_data_exfil.py | 数据泄露 (AWS 密钥外发) | 关卡 4 + 关卡 3 → DENY |
| 03 | demo/scenarios/scenario_03_hitl_approval.py | 高危操作 HITL 审批 | 关卡 2 → REQUIRE_APPROVAL |

# 靶子 MCP server

    python -m demo.targets.ops_target          # 以 stdio 方式启动

# 运行单个场景（不需要 LLM，直接构造 GateContext）

    python -m demo.scenarios.scenario_01_indirect_injection
    python -m demo.scenarios.scenario_02_data_exfil
    python -m demo.scenarios.scenario_03_hitl_approval

# 注意事项

- 3 个场景脚本可在关卡 stub 状态下运行，会显示当前实际决策和 stub 提示。
- 关卡 1/2/3/4 实现完整后，场景 01/02/03 将依次显示真实拦截效果。
"""
