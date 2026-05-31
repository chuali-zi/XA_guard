from __future__ import annotations

from bench.metrics import compute
from xa_guard.types import BenchCase, BenchResult, Decision, TaintLabel


def _result(case_id: str, expected: Decision, actual: Decision) -> BenchResult:
    return BenchResult(
        case=BenchCase(
            case_id=case_id,
            dimension="data_safety",
            attack_type="benign" if expected == Decision.ALLOW else "attack",
            input_payload={},
            expected_decision=expected,
        ),
        actual_decision=actual,
        actual_taint=TaintLabel.PUBLIC,
        rule_hits=[],
        latency_ms=1.0,
        passed=actual == expected,
    )


def test_warn_on_legal_task_counts_as_completed_not_false_positive() -> None:
    metrics = compute([
        _result("benign-warn", Decision.ALLOW, Decision.WARN),
        _result("attack-deny", Decision.DENY, Decision.DENY),
    ])

    assert metrics.fpr == 0.0
    assert metrics.cup == 1.0
    assert metrics.by_dimension["data_safety"]["fpr"] == 0.0
    assert metrics.by_dimension["data_safety"]["cup"] == 1.0
