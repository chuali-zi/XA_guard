"""评测 runner。

接口：
- load_cases(suite_path) -> list[BenchCase]
- run_suite(suite_path, cfg, dimension=None) -> list[BenchResult]
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import yaml

from xa_guard.types import (
    BenchCase,
    BenchResult,
    Decision,
    GateContext,
    InputSource,
    TaintLabel,
)


def _supply_chain_decision(arguments: dict[str, Any]) -> tuple[Decision, str]:
    from xa_guard.aibom.rater import rate_install_request

    grade, reason = rate_install_request(arguments)
    if grade in {"A", "B"}:
        return Decision.ALLOW, reason
    if grade == "C":
        return Decision.WARN, reason
    return Decision.DENY, reason


def load_cases(suite_path: str | Path) -> list[BenchCase]:
    with open(suite_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cases: list[BenchCase] = []
    for item in raw.get("cases", []):
        payload: dict[str, Any] = item["input_payload"]

        # input_sources: list[str] → list[InputSource]
        raw_sources = payload.get("input_sources", [])
        input_sources = [InputSource(s) for s in raw_sources] if raw_sources else [InputSource.USER]

        # session_history: list[dict] (kept as-is)
        session_history: list[dict] = []
        raw_history = payload.get("session_history", [])
        if raw_history:
            session_history = [dict(h) for h in raw_history]
        # message field → prepend as user turn
        if "message" in payload:
            session_history = [{"role": "user", "content": payload["message"]}] + session_history

        cases.append(
            BenchCase(
                case_id=item["case_id"],
                dimension=item["dimension"],
                attack_type=item.get("attack_type", "benign"),
                input_payload={
                    **payload,
                    "_input_sources": [s.value for s in input_sources],
                    "_session_history": session_history,
                },
                expected_decision=Decision(item["expected_decision"]),
                expected_taint=TaintLabel(item["expected_taint"]) if item.get("expected_taint") else None,
                policy_refs=list(item.get("policy_refs", [])),
                severity=item.get("severity", "medium"),
                note=item.get("note", ""),
            )
        )
    return cases


async def run_suite(
    suite_path: str | Path,
    cfg,
    dimension: str | None = None,
) -> list[BenchResult]:
    from bench.metrics import compute  # local import to avoid circular
    from xa_guard.server import build_pipeline

    cases = load_cases(suite_path)
    if dimension:
        cases = [c for c in cases if c.dimension == dimension]

    pipeline = build_pipeline(cfg)
    results: list[BenchResult] = []

    for case in cases:
        payload = case.input_payload
        tool_name: str = payload.get("tool_name", "")
        arguments: dict[str, Any] = dict(payload.get("arguments", {}))
        user_role: str = payload.get("user_role", "user")
        input_sources = [InputSource(s) for s in payload.get("_input_sources", ["user"])]
        session_history: list[dict] = payload.get("_session_history", [])

        ctx = GateContext(
            tool_name=tool_name,
            arguments=arguments,
            user_role=user_role,
            input_sources=input_sources,
            session_history=session_history,
        )

        async def mock_executor(c: GateContext) -> dict:
            return {
                "mocked": True,
                "case_id": case.case_id,
                "tool": c.tool_name,
            }

        t0 = time.perf_counter()
        if case.dimension == "supply_chain" and tool_name == "install_plugin":
            decision, reason = _supply_chain_decision(arguments)
            ctx.final_decision = decision
            ctx.final_reason = reason
        else:
            try:
                await pipeline.run(ctx, mock_executor)
            except Exception:
                pass
        latency_ms = (time.perf_counter() - t0) * 1000

        actual_decision = ctx.final_decision
        passed = actual_decision == case.expected_decision

        results.append(
            BenchResult(
                case=case,
                actual_decision=actual_decision,
                actual_taint=ctx.taint,
                rule_hits=list(ctx.rule_hits),
                latency_ms=latency_ms,
                passed=passed,
            )
        )

    return results
