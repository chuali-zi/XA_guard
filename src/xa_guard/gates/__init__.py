"""6 关卡实现包。

每关卡独立一个 module，遵循 base.Gate 抽象类：
    gate1_input.py   方向 1（输入攻击识别）
    gate2_plan.py    方向 2（HITL 审批）
    gate3_policy.py  方向 2 + 应用价值（规则引擎）
    gate4_taint.py   方向 2（信息流污点）
    gate5_sandbox.py 方向 2（沙箱）
    gate6_audit.py   方向 4（审计溯源）
"""
from xa_guard.gates.base import Gate, GateStage

__all__ = ["Gate", "GateStage"]
