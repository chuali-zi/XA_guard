"""Validate Gate3 rule fixtures as hard positive/negative constraints."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from xa_guard.config import GateConfig
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.types import Decision, GateContext, InputSource, RiskLevel, TaintLabel

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "bench" / "cases" / "gate3-rule-fixtures.yaml"
DEFAULT_POLICY = ROOT / "policies" / "baseline" / "gate3_rules.yaml"
DEFAULT_SCHEMA = ROOT / "bench" / "schema" / "gate3-rule-fixtures.schema.json"

DECISIONS = {d.value for d in Decision}
RISKS = {r.value for r in RiskLevel}
TAINTS = {t.value for t in TaintLabel}
SOURCES = {s.value for s in InputSource}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _policy_ids(path: Path) -> set[str]:
    data = _load_yaml(path)
    return {str(rule["id"]) for rule in data.get("rules", []) or [] if rule.get("id")}


def _ctx(payload: dict[str, Any]) -> GateContext:
    input_sources = [
        InputSource(str(source))
        for source in payload.get("input_sources", ["user"])
    ]
    return GateContext(
        tool_name=str(payload.get("tool_name", "")),
        arguments=dict(payload.get("arguments", {}) or {}),
        user_role=str(payload.get("user_role", "user")),
        input_sources=input_sources,
        risk_level=RiskLevel(str(payload.get("risk_level", "green"))),
        taint=TaintLabel(str(payload.get("taint", "PUBLIC"))),
        session_history=list(payload.get("session_history", []) or []),
    )


class Validator:
    def __init__(self, fixture: dict[str, Any], policy_path: Path):
        self.fixture = fixture
        self.policy_path = policy_path
        self.policy_ids = _policy_ids(policy_path)
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.gate = Gate3Policy(
            GateConfig(
                enabled=True,
                options={"backend": "python", "policy_file": str(policy_path)},
            )
        )

    def _check_case_shape(self, rule_id: str, label: str, case: Any) -> None:
        prefix = f"{rule_id}.{label}"
        if not isinstance(case, dict):
            self.errors.append(f"{prefix}: case must be an object")
            return
        if not case.get("case_id"):
            self.errors.append(f"{prefix}: missing case_id")
        payload = case.get("input_payload")
        if not isinstance(payload, dict) or not payload.get("tool_name"):
            self.errors.append(f"{prefix}: input_payload.tool_name is required")
            return
        if case.get("expected_hit") not in (True, False):
            self.errors.append(f"{prefix}: expected_hit must be boolean")
        decision = case.get("expected_decision")
        if decision is not None and decision not in DECISIONS:
            self.errors.append(f"{prefix}: expected_decision `{decision}` is invalid")
        risk = payload.get("risk_level")
        if risk is not None and risk not in RISKS:
            self.errors.append(f"{prefix}: risk_level `{risk}` is invalid")
        taint = payload.get("taint")
        if taint is not None and taint not in TAINTS:
            self.errors.append(f"{prefix}: taint `{taint}` is invalid")
        for source in payload.get("input_sources", []) or []:
            if source not in SOURCES:
                self.errors.append(f"{prefix}: input source `{source}` is invalid")

    def _evaluate_case(self, rule_id: str, label: str, case: dict[str, Any]) -> None:
        prefix = f"{rule_id}.{label}"
        payload = case.get("input_payload", {}) or {}
        try:
            result = self.gate.evaluate(_ctx(payload))
        except Exception as exc:
            self.errors.append(f"{prefix}: evaluation failed: {exc}")
            return

        expected_hit = bool(case["expected_hit"])
        actual_hit = rule_id in result.rule_hits
        if actual_hit != expected_hit:
            self.errors.append(
                f"{prefix}: expected_hit={expected_hit} but hits={result.rule_hits}"
            )
        expected_decision = case.get("expected_decision")
        if expected_decision is not None and result.decision.value != expected_decision:
            self.errors.append(
                f"{prefix}: expected_decision={expected_decision} but got {result.decision.value}"
            )

    def run(self) -> tuple[list[str], list[str]]:
        if not DEFAULT_SCHEMA.exists():
            self.errors.append(f"schema missing: {DEFAULT_SCHEMA}")

        fixtures = self.fixture.get("fixtures")
        if not isinstance(fixtures, list) or not fixtures:
            self.errors.append("fixtures must be a non-empty list")
            return self.errors, self.warnings

        seen: set[str] = set()
        positive = 0
        negative = 0
        for item in fixtures:
            if not isinstance(item, dict):
                self.errors.append("fixture item must be an object")
                continue
            rule_id = str(item.get("rule_id", ""))
            if not rule_id:
                self.errors.append("fixture item missing rule_id")
                continue
            if rule_id in seen:
                self.errors.append(f"duplicate fixture for rule_id `{rule_id}`")
            seen.add(rule_id)
            if rule_id not in self.policy_ids:
                self.errors.append(f"fixture references unknown rule_id `{rule_id}`")

            for label in ("positive", "negative"):
                case = item.get(label)
                self._check_case_shape(rule_id, label, case)
                if isinstance(case, dict):
                    if label == "positive":
                        positive += 1
                    else:
                        negative += 1

        missing = sorted(self.policy_ids - seen)
        extra = sorted(seen - self.policy_ids)
        if missing:
            self.errors.append("missing fixtures for rules: " + ", ".join(missing))
        if extra:
            self.errors.append("extra fixtures for non-policy rules: " + ", ".join(extra))

        if not self.errors:
            for item in fixtures:
                rule_id = str(item["rule_id"])
                self._evaluate_case(rule_id, "positive", item["positive"])
                self._evaluate_case(rule_id, "negative", item["negative"])

        self.summary = {
            "rules": len(self.policy_ids),
            "fixtures": len(fixtures),
            "positive": positive,
            "negative": negative,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
        }
        return self.errors, self.warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        fixture = _load_yaml(args.fixture)
    except FileNotFoundError:
        print(f"[ERROR] fixture not found: {args.fixture}", file=sys.stderr)
        return 2

    validator = Validator(fixture, args.policy)
    errors, warnings = validator.run()
    summary = getattr(
        validator,
        "summary",
        {"rules": len(validator.policy_ids), "fixtures": 0, "positive": 0, "negative": 0},
    )

    if args.json:
        print(json.dumps({**summary, "errors_detail": errors, "warnings_detail": warnings}, indent=2))
    else:
        for err in errors:
            print(f"[ERROR] {err}")
        for warn in warnings:
            print(f"[warn] {warn}")
        print(
            "[gate3-fixtures] rules={rules} fixtures={fixtures} positive={positive} "
            "negative={negative} errors={errors} warnings={warnings}".format(
                **summary
            )
        )

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
