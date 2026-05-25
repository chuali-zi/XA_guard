"""XA-Bench CLI。

用法：
    xa-bench run --suite bench/cases/csab-gov-mini-seed.yaml --config configs/xa-guard.yaml
    xa-bench run --suite ... --dimension content_safety
    xa-bench report --results bench/.log/last_results.json --format html
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from bench.metrics import compute
from bench.runner import load_cases, run_suite
from xa_guard.config import XAGuardConfig
from xa_guard.types import Decision, TaintLabel


def _results_to_json(results) -> list[dict]:
    out = []
    for r in results:
        out.append(
            {
                "case_id": r.case.case_id,
                "dimension": r.case.dimension,
                "attack_type": r.case.attack_type,
                "expected_decision": r.case.expected_decision.value,
                "actual_decision": r.actual_decision.value,
                "actual_taint": r.actual_taint.value if r.actual_taint else None,
                "rule_hits": r.rule_hits,
                "latency_ms": round(r.latency_ms, 2),
                "passed": r.passed,
                "severity": r.case.severity,
                "note": r.case.note,
            }
        )
    return out


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = XAGuardConfig.from_yaml(args.config)
    results = asyncio.run(run_suite(args.suite, cfg, dimension=args.dimension))

    report = compute(results)
    out_dir = Path("bench/.log")
    out_dir.mkdir(parents=True, exist_ok=True)

    results_json = _results_to_json(results)
    (out_dir / "last_results.json").write_text(
        json.dumps(results_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "last_report.json").write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # HTML report
    from bench.reporters.html_report import render_html
    render_html(results, report, out_path=out_dir / "report.html")

    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    print(f"\n[bench/.log/last_results.json, last_report.json, report.html] 已写出", file=sys.stderr)
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    results_path = Path(args.results)
    if not results_path.exists():
        print(f"results file not found: {results_path}", file=sys.stderr)
        return 1

    raw = json.loads(results_path.read_text(encoding="utf-8"))

    if args.format == "json":
        print(json.dumps(raw, ensure_ascii=False, indent=2))
        return 0

    # HTML: need to reconstruct BenchResult objects from JSON
    from bench.metrics import MetricsReport
    from bench.reporters.html_report import render_html
    from xa_guard.types import BenchCase, BenchResult, Decision, TaintLabel

    reconstructed = []
    for item in raw:
        case = BenchCase(
            case_id=item["case_id"],
            dimension=item["dimension"],
            attack_type=item.get("attack_type", "benign"),
            input_payload={},
            expected_decision=Decision(item["expected_decision"]),
            severity=item.get("severity", "medium"),
            note=item.get("note", ""),
        )
        reconstructed.append(
            BenchResult(
                case=case,
                actual_decision=Decision(item["actual_decision"]),
                actual_taint=TaintLabel(item["actual_taint"]) if item.get("actual_taint") else None,
                rule_hits=item.get("rule_hits", []),
                latency_ms=float(item.get("latency_ms", 0)),
                passed=bool(item.get("passed", False)),
                note=item.get("note", ""),
            )
        )

    metrics = compute(reconstructed)
    out_dir = Path("bench/.log")
    out_dir.mkdir(parents=True, exist_ok=True)
    html = render_html(reconstructed, metrics, out_path=out_dir / "report.html")
    print(f"HTML 报告已写出: {out_dir / 'report.html'}", file=sys.stderr)
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="xa-bench")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="跑评测 suite")
    p_run.add_argument("--suite", required=True)
    p_run.add_argument("--config", default="configs/xa-guard.yaml")
    p_run.add_argument("--dimension", default=None, help="过滤维度（可选）")
    p_run.set_defaults(func=_cmd_run)

    p_rep = sub.add_parser("report", help="生成报告")
    p_rep.add_argument("--results", required=True)
    p_rep.add_argument("--format", default="html", choices=["html", "json"])
    p_rep.set_defaults(func=_cmd_report)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
