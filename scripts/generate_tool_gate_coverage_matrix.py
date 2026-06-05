"""Generate a tool x gate coverage matrix for baseline policies.

The matrix makes Gate2/Gate3/Gate4 registration drift visible:
  - Gate2: tool risk exists in gate2_tool_risks.yaml.
  - Gate3: tool appears as at least one rule trigger in gate3_rules.yaml.
  - Gate4: tool capability exists in gate4_capabilities.yaml.
  - Bench: tool appears in csab-gov-mini-seed.yaml input_payload.tool_name.
  - Gate2/Gate4 risk_level values match for tools registered in both.

By default the script writes bench/.log/tool_gate_coverage.md and exits 0.
With --strict it exits non-zero on missing Gate2/Gate4 registrations for
Gate3 triggers, Gate2/Gate4 risk mismatches, or invalid risk/taint values.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GATE2 = ROOT / "policies" / "baseline" / "gate2_tool_risks.yaml"
DEFAULT_GATE3 = ROOT / "policies" / "baseline" / "gate3_rules.yaml"
DEFAULT_GATE4 = ROOT / "policies" / "baseline" / "gate4_capabilities.yaml"
DEFAULT_BENCH = ROOT / "bench" / "cases" / "csab-gov-mini-seed.yaml"
DEFAULT_REPORT = ROOT / "bench" / ".log" / "tool_gate_coverage.md"
RISKS = {"green", "yellow", "red"}
TAINTS = {"PUBLIC", "INTERNAL", "CONFIDENTIAL"}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_gate2(path: Path) -> dict[str, str]:
    data = _load_yaml(path)
    return dict(data.get("tool_risks", {}) or {})


def _load_gate3(path: Path) -> dict[str, list[str]]:
    data = _load_yaml(path)
    by_tool: dict[str, list[str]] = defaultdict(list)
    for rule in data.get("rules", []) or []:
        rule_id = rule.get("id")
        if not rule_id:
            continue
        for trigger in rule.get("triggers", []) or []:
            by_tool[str(trigger)].append(str(rule_id))
    return {tool: sorted(set(rules)) for tool, rules in by_tool.items()}


def _load_gate4(path: Path) -> dict[str, dict[str, Any]]:
    data = _load_yaml(path)
    tools: dict[str, dict[str, Any]] = {}
    for item in data.get("tools", []) or []:
        name = item.get("tool_name")
        if name:
            tools[str(name)] = item
    return tools


def _load_bench(path: Path) -> dict[str, dict[str, Any]]:
    data = _load_yaml(path)
    by_tool: dict[str, dict[str, Any]] = {}
    for case in data.get("cases", []) or []:
        payload = case.get("input_payload", {}) or {}
        tool = payload.get("tool_name")
        if not tool:
            continue
        item = by_tool.setdefault(
            str(tool),
            {
                "case_count": 0,
                "case_ids": [],
                "expected_decisions": set(),
                "case_kinds": set(),
            },
        )
        item["case_count"] += 1
        if case.get("case_id"):
            item["case_ids"].append(str(case["case_id"]))
        if case.get("expected_decision"):
            item["expected_decisions"].add(str(case["expected_decision"]))
        if case.get("case_kind"):
            item["case_kinds"].add(str(case["case_kind"]))

    for item in by_tool.values():
        item["expected_decisions"] = sorted(item["expected_decisions"])
        item["case_kinds"] = sorted(item["case_kinds"])
    return by_tool


def _status_for(
    *,
    gate2_risk: str | None,
    gate3_rules: list[str],
    gate4_item: dict[str, Any] | None,
    gate4_risk: str | None,
    bench_item: dict[str, Any] | None,
) -> str:
    present_count = sum([gate2_risk is not None, bool(gate3_rules), gate4_item is not None, bench_item is not None])
    if bench_item and present_count == 1:
        return "BENCH_ONLY"
    if gate3_rules and gate2_risk is None:
        return "MISSING_GATE2"
    if gate3_rules and gate4_item is None:
        return "MISSING_GATE4"
    if gate2_risk is not None and gate4_risk is not None and gate2_risk != gate4_risk:
        return "RISK_MISMATCH"
    if gate2_risk is not None and gate2_risk not in RISKS:
        return "INVALID_RISK"
    if gate4_risk is not None and gate4_risk not in RISKS:
        return "INVALID_RISK"
    if gate4_item is not None:
        if gate4_item.get("input_max_taint") not in TAINTS or gate4_item.get("output_taint") not in TAINTS:
            return "INVALID_TAINT"
    if gate3_rules and not bench_item:
        return "NO_BENCH_CASE"
    if not gate3_rules and bench_item:
        return "NO_GATE3_RULE"
    if gate2_risk is not None and gate4_item is None:
        return "GATE2_ONLY"
    if gate4_item is not None and gate2_risk is None:
        return "GATE4_ONLY"
    return "OK"


def build_matrix(
    gate2_path: Path = DEFAULT_GATE2,
    gate3_path: Path = DEFAULT_GATE3,
    gate4_path: Path = DEFAULT_GATE4,
    bench_path: Path = DEFAULT_BENCH,
) -> dict[str, Any]:
    gate2 = _load_gate2(gate2_path)
    gate3 = _load_gate3(gate3_path)
    gate4 = _load_gate4(gate4_path)
    bench = _load_bench(bench_path)

    tools = sorted(set(gate2) | set(gate3) | set(gate4) | set(bench))
    rows: list[dict[str, Any]] = []
    missing_gate2_for_gate3: list[str] = []
    missing_gate4_for_gate3: list[str] = []
    risk_mismatches: list[str] = []
    bench_only: list[str] = []
    gate3_without_bench: list[str] = []
    invalid_risk: list[str] = []
    invalid_taint: list[str] = []

    for tool in tools:
        gate2_risk = gate2.get(tool)
        gate3_rules = gate3.get(tool, [])
        gate4_item = gate4.get(tool)
        gate4_risk = gate4_item.get("risk_level") if gate4_item else None
        bench_item = bench.get(tool)

        if gate3_rules and gate2_risk is None:
            missing_gate2_for_gate3.append(tool)
        if gate3_rules and gate4_item is None:
            missing_gate4_for_gate3.append(tool)
        if gate2_risk is not None and gate4_risk is not None and gate2_risk != gate4_risk:
            risk_mismatches.append(tool)
        if bench_item and not gate2_risk and not gate3_rules and not gate4_item:
            bench_only.append(tool)
        if gate3_rules and not bench_item:
            gate3_without_bench.append(tool)
        if gate2_risk is not None and gate2_risk not in RISKS:
            invalid_risk.append(tool)
        if gate4_risk is not None and gate4_risk not in RISKS:
            invalid_risk.append(tool)
        if gate4_item is not None:
            if gate4_item.get("input_max_taint") not in TAINTS or gate4_item.get("output_taint") not in TAINTS:
                invalid_taint.append(tool)

        status = _status_for(
            gate2_risk=gate2_risk,
            gate3_rules=gate3_rules,
            gate4_item=gate4_item,
            gate4_risk=gate4_risk,
            bench_item=bench_item,
        )

        rows.append(
            {
                "tool": tool,
                "gate2_registered": gate2_risk is not None,
                "gate2_risk": gate2_risk or "-",
                "gate3_triggered": bool(gate3_rules),
                "gate3_rule_count": len(gate3_rules),
                "gate3_rules": gate3_rules,
                "gate4_registered": gate4_item is not None,
                "gate4_risk": gate4_risk or "-",
                "gate4_capabilities": gate4_item.get("capabilities", []) if gate4_item else [],
                "gate4_input_max_taint": gate4_item.get("input_max_taint", "-") if gate4_item else "-",
                "gate4_output_taint": gate4_item.get("output_taint", "-") if gate4_item else "-",
                "bench_present": bench_item is not None,
                "bench_case_count": bench_item["case_count"] if bench_item else 0,
                "bench_expected_decisions": bench_item["expected_decisions"] if bench_item else [],
                "bench_case_kinds": bench_item["case_kinds"] if bench_item else [],
                "status": status,
            }
        )

    summary = {
        "total_tools": len(tools),
        "gate2_tools": len(gate2),
        "gate3_trigger_tools": len(gate3),
        "gate4_tools": len(gate4),
        "bench_tools": len(bench),
        "missing_gate2_for_gate3": sorted(missing_gate2_for_gate3),
        "missing_gate4_for_gate3": sorted(missing_gate4_for_gate3),
        "risk_mismatches": sorted(risk_mismatches),
        "bench_only": sorted(bench_only),
        "gate3_without_bench": sorted(gate3_without_bench),
        "invalid_risk": sorted(set(invalid_risk)),
        "invalid_taint": sorted(set(invalid_taint)),
    }
    return {"summary": summary, "rows": rows}


def render_markdown(matrix: dict[str, Any]) -> str:
    summary = matrix["summary"]
    rows = matrix["rows"]
    lines: list[str] = []
    lines.append("# Tool x Gate coverage matrix")
    lines.append("")
    lines.append("Baseline files:")
    lines.append("")
    lines.append("- Gate2: `policies/baseline/gate2_tool_risks.yaml`")
    lines.append("- Gate3: `policies/baseline/gate3_rules.yaml`")
    lines.append("- Gate4: `policies/baseline/gate4_capabilities.yaml`")
    lines.append("- Bench: `bench/cases/csab-gov-mini-seed.yaml`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total distinct tools: **{summary['total_tools']}**")
    lines.append(f"- Gate2 registered tools: **{summary['gate2_tools']}**")
    lines.append(f"- Gate3 trigger tools: **{summary['gate3_trigger_tools']}**")
    lines.append(f"- Gate4 registered tools: **{summary['gate4_tools']}**")
    lines.append(f"- Bench tool names: **{summary['bench_tools']}**")
    lines.append(f"- Gate3 triggers missing Gate2 registration: **{len(summary['missing_gate2_for_gate3'])}**")
    lines.append(f"- Gate3 triggers missing Gate4 registration: **{len(summary['missing_gate4_for_gate3'])}**")
    lines.append(f"- Gate2/Gate4 risk mismatches: **{len(summary['risk_mismatches'])}**")
    lines.append(f"- Bench-only tools: **{len(summary['bench_only'])}**")
    lines.append(f"- Gate3 trigger tools without bench case: **{len(summary['gate3_without_bench'])}**")
    lines.append(f"- Invalid risk values: **{len(summary['invalid_risk'])}**")
    lines.append(f"- Invalid taint values: **{len(summary['invalid_taint'])}**")
    lines.append("")

    if summary["missing_gate2_for_gate3"]:
        lines.append("Missing Gate2 for Gate3 triggers: " + ", ".join(summary["missing_gate2_for_gate3"]))
        lines.append("")
    if summary["missing_gate4_for_gate3"]:
        lines.append("Missing Gate4 for Gate3 triggers: " + ", ".join(summary["missing_gate4_for_gate3"]))
        lines.append("")
    if summary["risk_mismatches"]:
        lines.append("Gate2/Gate4 risk mismatches: " + ", ".join(summary["risk_mismatches"]))
        lines.append("")
    if summary["bench_only"]:
        lines.append("Bench-only tools: " + ", ".join(summary["bench_only"]))
        lines.append("")
    if summary["gate3_without_bench"]:
        lines.append("Gate3 trigger tools without bench case: " + ", ".join(summary["gate3_without_bench"]))
        lines.append("")

    lines.append("## Matrix")
    lines.append("")
    lines.append("| Tool | Gate2 risk | Gate3 rules | Gate4 risk | Gate4 capabilities | Taint in/out | Bench cases | Bench decisions | Status |")
    lines.append("|---|---|---:|---|---|---|---:|---|---|")
    for row in rows:
        caps = ", ".join(row["gate4_capabilities"]) if row["gate4_capabilities"] else "-"
        taint = f"{row['gate4_input_max_taint']} / {row['gate4_output_taint']}"
        decisions = ", ".join(row["bench_expected_decisions"]) if row["bench_expected_decisions"] else "-"
        lines.append(
            "| {tool} | {gate2_risk} | {rule_count} | {gate4_risk} | {caps} | {taint} | {bench_cases} | {decisions} | {status} |".format(
                tool=row["tool"],
                gate2_risk=row["gate2_risk"],
                rule_count=row["gate3_rule_count"],
                gate4_risk=row["gate4_risk"],
                caps=caps,
                taint=taint,
                bench_cases=row["bench_case_count"],
                decisions=decisions,
                status=row["status"],
            )
        )
    lines.append("")

    lines.append("## Gate3 trigger detail")
    lines.append("")
    for row in rows:
        if row["gate3_rules"]:
            lines.append(f"- {row['tool']}: {', '.join(row['gate3_rules'])}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate2", type=Path, default=DEFAULT_GATE2)
    parser.add_argument("--gate3", type=Path, default=DEFAULT_GATE3)
    parser.add_argument("--gate4", type=Path, default=DEFAULT_GATE4)
    parser.add_argument("--bench", type=Path, default=DEFAULT_BENCH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    matrix = build_matrix(args.gate2, args.gate3, args.gate4, args.bench)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_markdown(matrix), encoding="utf-8")

    if args.json:
        print(json.dumps(matrix["summary"], ensure_ascii=False, indent=2))
    else:
        summary = matrix["summary"]
        print(
            "[coverage-matrix] tools={total_tools} gate2={gate2_tools} gate3_triggers={gate3_trigger_tools} "
            "gate4={gate4_tools} bench={bench_tools} missing_gate2={m2} missing_gate4={m4} "
            "risk_mismatches={rm} bench_only={bo} gate3_no_bench={g3nb}".format(
                **summary,
                m2=len(summary["missing_gate2_for_gate3"]),
                m4=len(summary["missing_gate4_for_gate3"]),
                rm=len(summary["risk_mismatches"]),
                bo=len(summary["bench_only"]),
                g3nb=len(summary["gate3_without_bench"]),
            )
        )
        print(f"[coverage-matrix] report -> {args.report}")

    has_gaps = (
        matrix["summary"]["missing_gate2_for_gate3"]
        or matrix["summary"]["missing_gate4_for_gate3"]
        or matrix["summary"]["risk_mismatches"]
        or matrix["summary"]["invalid_risk"]
        or matrix["summary"]["invalid_taint"]
    )
    if args.strict and has_gaps:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
