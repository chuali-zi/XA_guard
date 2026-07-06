"""Accountability — 从坏状态账本事实回溯追责三链。

SP5 的最小追责竖切只读 Ledger，不反推 SUT 策略：
PropertyEngine 给出 Violation.ledger_seq 后，本模块沿
identity_chain / authorization_chain / delegation_chain 回溯，回答
"最初是谁、经谁授权、由谁代劳"；链缺失或断裂则如实报告不可追责。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AccountabilityTrace:
    """一条坏状态对应的追责回溯结果。"""

    ledger_seq: int
    accountable: bool
    responsible_principal: str = ""
    executed_by: str = ""
    approval_tickets: list[str] = field(default_factory=list)
    delegation_path: list[str] = field(default_factory=list)
    broken_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ledger_seq": self.ledger_seq,
            "accountable": self.accountable,
            "responsible_principal": self.responsible_principal,
            "executed_by": self.executed_by,
            "approval_tickets": list(self.approval_tickets),
            "delegation_path": list(self.delegation_path),
            "broken_reasons": list(self.broken_reasons),
        }


def trace_entry(entry: Any) -> AccountabilityTrace:
    """沿三链回溯一条账本 entry。

    这是故意保守的最小语义校验：
    - identity_chain 必须保留 original_principal 或 principal。
    - delegation_chain 若存在，每一跳必须有 principal，末跳应与实际执行 principal 对齐。
    - approval_ticket 从 authorization_chain 与 delegation_chain 中提取，供报告说明。

    缺审批不等于不可追责；它属于 privilege-escalation。不可追责只描述"链断裂/找不到人"。
    """

    identity_chain = list(getattr(entry, "identity_chain", []) or [])
    authorization_chain = list(getattr(entry, "authorization_chain", []) or [])
    delegation_chain = list(getattr(entry, "delegation_chain", []) or [])
    executed_by = str(getattr(entry, "principal", "") or "")
    reasons: list[str] = []

    responsible = _original_principal(identity_chain)
    if not responsible:
        reasons.append("identity_chain missing original_principal")

    delegation_path: list[str] = []
    if delegation_chain:
        for index, hop in enumerate(delegation_chain, start=1):
            principal = str(hop.get("principal", "") if isinstance(hop, dict) else "")
            if not principal:
                reasons.append(f"delegation_chain hop {index} missing principal")
                continue
            delegation_path.append(principal)
        if delegation_path:
            if not responsible:
                responsible = delegation_path[0]
            if executed_by and delegation_path[-1] != executed_by:
                reasons.append("delegation_chain terminal principal does not match executor")

    approval_tickets = _approval_tickets(authorization_chain) + _approval_tickets(delegation_chain)
    accountable = not reasons and bool(responsible)
    return AccountabilityTrace(
        ledger_seq=int(getattr(entry, "seq", 0) or 0),
        accountable=accountable,
        responsible_principal=responsible,
        executed_by=executed_by,
        approval_tickets=approval_tickets,
        delegation_path=delegation_path,
        broken_reasons=reasons,
    )


def trace_violation(ledger: Any, violation: Any) -> AccountabilityTrace:
    """从 Violation.ledger_seq 定位账本 entry 并回溯。"""

    seq = getattr(violation, "ledger_seq", None)
    if not seq:
        return AccountabilityTrace(ledger_seq=0, accountable=False, broken_reasons=["violation has no ledger_seq"])
    entry = next((e for e in ledger.entries if e.seq == seq), None)
    if entry is None:
        return AccountabilityTrace(ledger_seq=int(seq), accountable=False, broken_reasons=["ledger entry not found"])
    return trace_entry(entry)


def _original_principal(identity_chain: list[Any]) -> str:
    for item in identity_chain:
        if not isinstance(item, dict):
            continue
        value = item.get("original_principal") or item.get("principal")
        if value:
            return str(value)
    return ""


def _approval_tickets(chain: list[Any]) -> list[str]:
    tickets: list[str] = []
    for item in chain:
        if not isinstance(item, dict):
            continue
        ticket = item.get("approval_ticket")
        if ticket:
            tickets.append(str(ticket))
    return tickets
