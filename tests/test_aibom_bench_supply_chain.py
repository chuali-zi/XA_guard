from __future__ import annotations

import asyncio

from bench.runner import run_suite
from xa_guard.config import XAGuardConfig
from xa_guard.types import Decision


def test_supply_chain_seed_cases_have_aibom_decisions() -> None:
    cfg = XAGuardConfig.from_yaml("configs/xa-guard.yaml")

    results = asyncio.run(run_suite("bench/cases/csab-gov-mini-seed.yaml", cfg, dimension="supply_chain"))

    decisions = {result.case.case_id: result.actual_decision for result in results}
    assert len(results) == 25
    assert {case_id: decisions[case_id] for case_id in ("SCM-001", "SCM-002", "SCM-003", "SCM-004")} == {
        "SCM-001": Decision.DENY,
        "SCM-002": Decision.WARN,
        "SCM-003": Decision.ALLOW,
        "SCM-004": Decision.DENY,
    }
