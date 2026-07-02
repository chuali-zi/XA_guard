"""P2 capability 5: risk-amount quantification (风险金额量化).

Scaffold only. See docs/02-goals-and-scope.md (P2 range item 5) and
docs/13-implementation-roadmap.md (P2 item 5). No runtime wiring yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import SCAFFOLD, CapabilitySpec, P2NotImplementedError


@dataclass(frozen=True)
class RiskScore:
    """Quantified monetary/impact risk for a single case or action.

    ``amount`` is expressed in synthetic range units (``currency='RANGE'``) and
    never represents real money.
    """

    case_id: str
    amount: float = 0.0
    currency: str = "RANGE"
    confidence: float = 0.0  # 0..1
    factors: dict[str, Any] = field(default_factory=dict)


class RiskModel:
    """Interface for scoring the monetary/impact risk of a case execution.

    Planned oracle fields: ``risk_amount_le``, ``risk_score_present``.
    Planned metrics: ``risk_weighted_asr``, ``expected_loss_avoided``.
    """

    def score(self, execution: Any) -> RiskScore:
        raise P2NotImplementedError("p2.risk.RiskModel.score is a scaffold stub")


SPEC = CapabilitySpec(
    key="risk",
    title="风险金额量化 / risk-amount quantification",
    module=__name__,
    roadmap_refs=("docs/02-goals-and-scope.md#P2-5", "docs/13-implementation-roadmap.md#P2-5"),
    summary="Quantify synthetic monetary/impact risk per case and expose risk-weighted metrics.",
    status=SCAFFOLD,
    planned_expected_fields=("risk_amount_le", "risk_score_present"),
    planned_metrics=("risk_weighted_asr", "expected_loss_avoided"),
)
