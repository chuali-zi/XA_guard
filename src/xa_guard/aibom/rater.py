"""插件安全评级 + 三段审批 — 赛题方向 3。

子 agent 实施职责：
- 输入 ScanReport → 输出评级（A/B/C/D/F）
- A/B 自动放行；C 人工复核；D/F 拒绝
- 接口预留"上线后行为漂移监测"占位
"""
from __future__ import annotations

from typing import Literal

from xa_guard.aibom.scanner import ScanReport

Grade = Literal["A", "B", "C", "D", "F"]


def rate(report: ScanReport) -> tuple[Grade, str]:
    """返回 (评级, 理由)。"""
    # TODO(agent-AIBOM): 实现评级
    return "C", "stub"
