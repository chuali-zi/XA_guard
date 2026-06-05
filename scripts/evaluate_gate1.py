"""Evaluate Gate1 in isolation against a benchmark suite.

This runner intentionally does not execute Gate2-Gate6 and does not modify
benchmark cases. It answers a narrower question than ``bench.runner``:

    Did Gate1 itself detect the input, which detector fired, and at what cost?

The default mode is rule-only so CI can run without model weights. Real model
verification can enable Qwen explicitly, for example:

    python scripts/evaluate_gate1.py --detectors rule,qwen --device cuda --dtype float16
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from xa_guard.config import GateConfig, XAGuardConfig
from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.types import Decision, GateContext, InputSource


BLOCKING_DECISIONS = {Decision.DENY, Decision.REQUIRE_APPROVAL}
DETECTION_DECISIONS = {Decision.WARN, Decision.DENY, Decision.REQUIRE_APPROVAL}
DEFAULT_GATE1_ATTACK_TYPES = frozenset(
    {
        "dangerous_command",
        "forbidden_generation",
        "indirect_injection",
        "jailbreak_or_prompt_leak",
        "pii_leak",
        "secret_exfil",
    }
)


@dataclass
class Gate1EvalCase:
    case_id: str
    dimension: str
    attack_type: str
    case_kind: str
    expected_decision: Decision
    input_payload: dict[str, Any]
    severity: str = "medium"
    note: str = ""


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 2)
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * pct)))
    return round(ordered[idx], 2)


def _load_cases(path: str | Path, dimension: str | None = None) -> list[Gate1EvalCase]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    cases: list[Gate1EvalCase] = []
    for item in raw.get("cases", []):
        if dimension and item.get("dimension") != dimension:
            continue
        cases.append(
            Gate1EvalCase(
                case_id=str(item["case_id"]),
                dimension=str(item["dimension"]),
                attack_type=str(item.get("attack_type", "")),
                case_kind=str(item.get("case_kind", "attack_case")),
                expected_decision=Decision(item["expected_decision"]),
                input_payload=dict(item["input_payload"]),
                severity=str(item.get("severity", "medium")),
                note=str(item.get("note", "")),
            )
        )
    return cases


def _ctx_from_payload(payload: dict[str, Any]) -> GateContext:
    raw_sources = payload.get("input_sources", [])
    input_sources = [InputSource(s) for s in raw_sources] if raw_sources else [InputSource.USER]

    session_history: list[dict[str, Any]] = []
    raw_history = payload.get("session_history", [])
    if raw_history:
        session_history = [dict(h) for h in raw_history]
    if "message" in payload:
        session_history = [{"role": "user", "content": payload["message"]}] + session_history

    return GateContext(
        tool_name=str(payload.get("tool_name", "")),
        arguments=dict(payload.get("arguments", {})),
        user_role=str(payload.get("user_role", "user")),
        input_sources=input_sources,
        session_history=session_history,
    )


def _gate1_options(
    cfg: XAGuardConfig,
    detectors: str,
    spotlighting: bool,
    device: str,
    dtype: str,
    dry_run: bool,
) -> dict[str, Any]:
    options = deepcopy(cfg.gate("gate1").options)
    configured = options.get("detectors", [])
    rule = next((d for d in configured if d.get("type") == "rule"), None)
    qwen = next((d for d in configured if d.get("backend") == "qwen3guard"), None)

    selected: list[dict[str, Any]] = []
    requested = {part.strip() for part in detectors.split(",") if part.strip()}
    if "rule" in requested:
        if rule is None:
            raise ValueError("config has no Gate1 rule detector")
        selected.append(deepcopy(rule))
    if "qwen" in requested or "qwen3guard" in requested:
        if qwen is None:
            raise ValueError("config has no qwen3guard detector")
        qwen_copy = deepcopy(qwen)
        qwen_copy["device"] = device
        qwen_copy.setdefault("options", {})
        qwen_copy["options"]["torch_dtype"] = dtype
        qwen_copy["options"]["dry_run"] = dry_run
        selected.append(qwen_copy)

    if not selected:
        raise ValueError("no detectors selected; use rule, qwen, or rule,qwen")

    options["detectors"] = selected
    options["spotlighting"] = {"enabled": spotlighting}
    return options


def _max_label_score(labels: list[dict[str, Any]]) -> float:
    scores = [float(label.get("score", 0.0) or 0.0) for label in labels]
    return max(scores) if scores else 0.0


def _threshold_metrics(rows: list[dict[str, Any]], fpr_limits: list[float]) -> dict[str, Any]:
    attacks = [r for r in rows if r["case_kind"] == "attack_case"]
    benign = [r for r in rows if r["case_kind"] == "benign_control"]
    thresholds = sorted({_max_label_score(r["all_labels"]) for r in rows} | {0.0, 0.5, 1.0}, reverse=True)
    points = []
    for threshold in thresholds:
        attack_hits = [r for r in attacks if _max_label_score(r["all_labels"]) >= threshold]
        benign_hits = [r for r in benign if _max_label_score(r["all_labels"]) >= threshold]
        recall = len(attack_hits) / len(attacks) if attacks else 0.0
        fpr = len(benign_hits) / len(benign) if benign else 0.0
        points.append({"threshold": threshold, "recall": recall, "fpr": fpr})

    by_limit: dict[str, Any] = {}
    for limit in fpr_limits:
        valid = [p for p in points if p["fpr"] <= limit]
        best = max(valid, key=lambda p: (p["recall"], p["threshold"]), default=None)
        by_limit[str(limit)] = (
            {
                "recall": round(best["recall"], 4),
                "threshold": round(best["threshold"], 4),
                "fpr": round(best["fpr"], 4),
            }
            if best
            else {"recall": 0.0, "threshold": None, "fpr": None}
        )
    return {"points": points, "recall_at_fpr": by_limit}


def _scope_metrics(rows: list[dict[str, Any]], attack_types: set[str]) -> dict[str, Any]:
    attacks = [r for r in rows if r["case_kind"] == "attack_case" and r["attack_type"] in attack_types]
    benign = [r for r in rows if r["case_kind"] == "benign_control"]
    missed = [r for r in attacks if not r["detected"]]
    detected_benign = [r for r in benign if r["detected"]]
    blocked_benign = [r for r in benign if r["blocked"]]
    return {
        "attack_types": sorted(attack_types),
        "attacks": len(attacks),
        "benign_controls": len(benign),
        "detection_recall": round(1.0 - (len(missed) / len(attacks) if attacks else 0.0), 4),
        "asr": round(len(missed) / len(attacks), 4) if attacks else 0.0,
        "fpr_any_detection": round(len(detected_benign) / len(benign), 4) if benign else 0.0,
        "fpr_blocking": round(len(blocked_benign) / len(benign), 4) if benign else 0.0,
        "false_negatives": [
            {
                "case_id": r["case_id"],
                "dimension": r["dimension"],
                "attack_type": r["attack_type"],
                "decision": r["gate1_decision"],
                "latency_ms": r["latency_ms"],
                "note": r["note"],
            }
            for r in missed
        ],
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    cfg = XAGuardConfig.from_yaml(args.config)
    gate_cfg = GateConfig(
        enabled=True,
        options=_gate1_options(
            cfg=cfg,
            detectors=args.detectors,
            spotlighting=not args.no_spotlighting,
            device=args.device,
            dtype=args.dtype,
            dry_run=args.dry_run,
        ),
    )
    gate = Gate1Input(gate_cfg)
    cases = _load_cases(args.suite, dimension=args.dimension)

    rows: list[dict[str, Any]] = []
    for case in cases:
        ctx = _ctx_from_payload(case.input_payload)
        t0 = time.perf_counter()
        result = gate.evaluate(ctx)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        detectors = result.metadata.get("detectors", [])
        all_labels = result.metadata.get("all_labels", [])
        spotlighting = result.metadata.get("spotlighting", {})
        rows.append(
            {
                "case_id": case.case_id,
                "dimension": case.dimension,
                "attack_type": case.attack_type,
                "case_kind": case.case_kind,
                "severity": case.severity,
                "expected_decision": case.expected_decision.value,
                "gate1_decision": result.decision.value,
                "detected": result.decision in DETECTION_DECISIONS,
                "blocked": result.decision in BLOCKING_DECISIONS,
                "risks": result.risks,
                "detectors": detectors,
                "spotlighting": spotlighting,
                "all_labels": all_labels,
                "latency_ms": round(elapsed_ms, 2),
                "note": case.note,
            }
        )

    attacks = [r for r in rows if r["case_kind"] == "attack_case"]
    benign = [r for r in rows if r["case_kind"] == "benign_control"]
    attack_allowed = [r for r in attacks if not r["detected"]]
    benign_detected = [r for r in benign if r["detected"]]
    benign_blocked = [r for r in benign if r["blocked"]]
    latencies = [float(r["latency_ms"]) for r in rows]

    detector_totals: dict[str, dict[str, Any]] = {}
    for row in rows:
        for detector in row["detectors"]:
            item = detector_totals.setdefault(
                detector["name"],
                {"available": 0, "unavailable": 0, "labels": 0, "latencies": []},
            )
            if detector.get("available"):
                item["available"] += 1
            else:
                item["unavailable"] += 1
            item["labels"] += int(detector.get("labels", 0) or 0)
            if detector.get("latency_ms") is not None:
                item["latencies"].append(float(detector["latency_ms"]))
    for item in detector_totals.values():
        item["latency_p50_ms"] = _percentile(item.pop("latencies"), 0.5)

    spotlighted_rows = [r for r in rows if r.get("spotlighting", {}).get("applied")]

    by_attack_type: dict[str, dict[str, Any]] = {}
    for attack_type in sorted({r["attack_type"] for r in attacks}):
        subset = [r for r in attacks if r["attack_type"] == attack_type]
        misses = [r for r in subset if not r["detected"]]
        by_attack_type[attack_type] = {
            "total": len(subset),
            "missed": len(misses),
            "recall": round(1.0 - (len(misses) / len(subset) if subset else 0.0), 4),
        }

    gate1_attack_types = (
        {part.strip() for part in args.gate1_attack_types.split(",") if part.strip()}
        if args.gate1_attack_types
        else set(DEFAULT_GATE1_ATTACK_TYPES)
    )

    summary = {
        "suite": args.suite,
        "config": args.config,
        "dimension": args.dimension,
        "detectors": args.detectors,
        "spotlighting": not args.no_spotlighting,
        "device": args.device,
        "dtype": args.dtype,
        "dry_run": args.dry_run,
        "total": len(rows),
        "attacks": len(attacks),
        "benign_controls": len(benign),
        "detection_recall": round(1.0 - (len(attack_allowed) / len(attacks) if attacks else 0.0), 4),
        "asr": round(len(attack_allowed) / len(attacks), 4) if attacks else 0.0,
        "fpr_any_detection": round(len(benign_detected) / len(benign), 4) if benign else 0.0,
        "fpr_blocking": round(len(benign_blocked) / len(benign), 4) if benign else 0.0,
        "latency_p50_ms": _percentile(latencies, 0.5),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "detectors_summary": detector_totals,
        "spotlighting_summary": {
            "enabled": not args.no_spotlighting,
            "applied_cases": len(spotlighted_rows),
            "applied_attack_cases": len([r for r in spotlighted_rows if r["case_kind"] == "attack_case"]),
            "sources": sorted(
                {
                    source
                    for r in spotlighted_rows
                    for source in r.get("spotlighting", {}).get("untrusted_sources", [])
                }
            ),
        },
        "by_attack_type": by_attack_type,
        "gate1_scope": _scope_metrics(rows, gate1_attack_types),
        "score_thresholds": _threshold_metrics(rows, [0.01, 0.05]),
        "false_negatives": [
            {
                "case_id": r["case_id"],
                "dimension": r["dimension"],
                "attack_type": r["attack_type"],
                "decision": r["gate1_decision"],
                "latency_ms": r["latency_ms"],
                "note": r["note"],
            }
            for r in attack_allowed
        ],
        "false_positives": [
            {
                "case_id": r["case_id"],
                "dimension": r["dimension"],
                "attack_type": r["attack_type"],
                "decision": r["gate1_decision"],
                "latency_ms": r["latency_ms"],
                "note": r["note"],
            }
            for r in benign_detected
        ],
    }
    if args.include_rows:
        summary["rows"] = rows
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Gate1 only against a benchmark suite")
    parser.add_argument("--suite", default="bench/cases/csab-gov-mini-seed.yaml")
    parser.add_argument("--config", default="configs/xa-guard.yaml")
    parser.add_argument("--dimension", default=None)
    parser.add_argument("--detectors", default="rule", help="comma list: rule, qwen, rule,qwen")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--dtype", default="float32")
    parser.add_argument("--dry-run", action="store_true", help="force model backend dry-run mode")
    parser.add_argument("--no-spotlighting", action="store_true")
    parser.add_argument("--include-rows", action="store_true")
    parser.add_argument(
        "--gate1-attack-types",
        default="",
        help="comma list for Gate1-scope metrics; default covers prompt/tool-output/data-exfil input attacks",
    )
    parser.add_argument("--out", default="", help="optional JSON output path; omitted means stdout only")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress stdout when writing large evaluation payloads with --out",
    )
    args = parser.parse_args()

    result = evaluate(args)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    if not args.quiet:
        print(payload)


if __name__ == "__main__":
    main()
