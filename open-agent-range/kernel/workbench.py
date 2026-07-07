"""SP4 red-team workbench CLI.

This module is intentionally thin and stdlib-only. It lets a red teamer inspect
available worlds/surfaces, create a finding, run deterministic offline A/B, read
evidence summaries, and promote a reviewed finding into challenge data.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kernel.demo import reference_surface
from kernel.evidence import EvidenceStore
from kernel.injection import Injection
from kernel.ledger import Ledger
from kernel.policy_overlay import overlay_from_scenario
from kernel.run import run_attempt
from kernel.scenario import Scenario, load_injections, load_scenario, with_injections
from kernel.seat import GullibleSeat, ManualSeat, SeatContext
from kernel.sut import GuardStubSUT, NullSUT, SUT, ToolCall, XaGuardSUT


DEFAULT_WORLD_DIR = Path("scenarios") / "dctg"
DEFAULT_FINDINGS_DIR = Path(".runtime") / "findings"
DEFAULT_AB_DIR = Path(".runtime") / "ab"
DEFAULT_CHALLENGES_DIR = Path("scenarios") / "challenges"
FINDING_STATUSES = {"draft", "reproduced", "rejected", "promoted"}
REVIEW_STATUSES = {"draft", "reproduced", "rejected"}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Open Agent Range SP4 red-team workbench")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("worlds", help="list scenarios/dctg/*.json")

    surfaces = sub.add_parser("surfaces", help="show injection surfaces, seat channels, and tools")
    surfaces.add_argument("--world", required=True)

    init = sub.add_parser("init-finding", help="create a finding draft JSON")
    init.add_argument("--world", required=True)
    init.add_argument("--target", required=True)
    init.add_argument("--payload", required=True)
    init.add_argument("--task-prompt", required=True)
    init.add_argument("--out")
    init.add_argument("--expected-risk", default="sensitive-egress")
    init.add_argument("--notes", default="")

    list_findings = sub.add_parser("list-findings", help="list finding queue items")
    list_findings.add_argument("--dir", default=str(DEFAULT_FINDINGS_DIR))
    list_findings.add_argument("--status", choices=sorted(FINDING_STATUSES))
    list_findings.add_argument("--json", action="store_true", help="emit JSON list")

    validate = sub.add_parser("validate-finding", help="validate a finding JSON")
    validate.add_argument("--finding", required=True)
    validate.add_argument("--json", action="store_true", help="emit JSON result")

    manual = sub.add_parser("manual-attempt", help="run one manual red-team ToolCall through a selected SUT")
    manual.add_argument("--world", required=True)
    manual.add_argument("--principal", required=True)
    manual.add_argument("--tool", required=True)
    manual.add_argument("--args-json", default="{}", help="JSON object passed as the tool args")
    manual.add_argument("--inject", action="append", default=[], help="optional injection fixture JSON; may repeat")
    manual.add_argument("--out-dir", "--evidence-dir", dest="out_dir")
    manual.add_argument("--sut-mode", default="guard", choices=["null", "guard", "guardstub", "xaguard", "xa-guard"])
    manual.add_argument("--live", action="store_true", help="use live XA-Guard when --sut-mode xaguard")
    manual.add_argument("--xa-guard-root", help="path to the external XA-Guard repository for live mode")
    manual.add_argument("--task", default="manual red-team attempt")
    manual.add_argument("--json", action="store_true", help="emit JSON summary")

    manual_session = sub.add_parser("manual-session", help="run multiple manual ToolCalls through a selected SUT")
    manual_session.add_argument("--world", required=True)
    manual_session.add_argument("--principal", required=True)
    calls_source = manual_session.add_mutually_exclusive_group(required=True)
    calls_source.add_argument("--calls-json", help="JSON list of {'tool': name, 'args': object} calls")
    calls_source.add_argument("--calls-file", help="path to a JSON file containing the call list")
    manual_session.add_argument("--inject", action="append", default=[], help="optional injection fixture JSON; may repeat")
    manual_session.add_argument("--out-dir", "--evidence-dir", dest="out_dir")
    manual_session.add_argument("--sut-mode", default="guard", choices=["null", "guard", "guardstub", "xaguard", "xa-guard"])
    manual_session.add_argument("--live", action="store_true", help="use live XA-Guard when --sut-mode xaguard")
    manual_session.add_argument("--xa-guard-root", help="path to the external XA-Guard repository for live mode")
    manual_session.add_argument("--task", default="manual multi-step red-team session")
    manual_session.add_argument("--json", action="store_true", help="emit JSON summary")

    review = sub.add_parser("review-finding", help="write human review status and notes")
    review.add_argument("--finding", required=True)
    review.add_argument("--status", required=True, choices=sorted(REVIEW_STATUSES))
    review.add_argument("--notes", required=True)

    run_ab = sub.add_parser("run-ab", help="run a finding against NullSUT vs a protected SUT")
    run_ab.add_argument("--finding", required=True)
    run_ab.add_argument("--out-dir", "--evidence-dir", dest="out_dir")
    run_ab.add_argument("--agent", choices=["gullible"], default="gullible")
    run_ab.add_argument("--runs", "--repeat", dest="runs", type=int, default=1)
    run_ab.add_argument(
        "--sut-mode",
        default="null,guard",
        help="protected side to compare with null: guard/guardstub/null,guard or xaguard/null,xaguard",
    )
    run_ab.add_argument("--live", action="store_true", help="use live XA-Guard for --sut-mode xaguard")
    run_ab.add_argument("--xa-guard-root", help="path to the external XA-Guard repository for live mode")
    mode = run_ab.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the plan without running attempts")
    mode.add_argument("--execute", action="store_true", help="write null/guard evidence and summary.json")

    show = sub.add_parser("show", help="summarize an attempt directory or A/B output directory")
    show.add_argument("path")
    show.add_argument("--json", action="store_true", help="emit JSON summary")

    promote = sub.add_parser("promote", help="convert a reviewed finding into challenge data")
    promote.add_argument("--finding", required=True)
    promote.add_argument("--out")
    promote.add_argument("--force", action="store_true", help="overwrite an existing challenge file")

    args = parser.parse_args(argv)
    if args.command == "worlds":
        return _cmd_worlds()
    if args.command == "surfaces":
        return _cmd_surfaces(args)
    if args.command == "init-finding":
        return _cmd_init_finding(args)
    if args.command == "list-findings":
        return _cmd_list_findings(args)
    if args.command == "validate-finding":
        return _cmd_validate_finding(args)
    if args.command == "manual-attempt":
        return _cmd_manual_attempt(args)
    if args.command == "manual-session":
        return _cmd_manual_session(args)
    if args.command == "review-finding":
        return _cmd_review_finding(args)
    if args.command == "run-ab":
        return _cmd_run_ab(args)
    if args.command == "show":
        return _cmd_show(args)
    if args.command == "promote":
        return _cmd_promote(args)
    raise AssertionError(f"unhandled command: {args.command}")


def _cmd_worlds() -> int:
    worlds = sorted(DEFAULT_WORLD_DIR.glob("*.json"))
    for path in worlds:
        print(path.as_posix())
    return 0


def _cmd_surfaces(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.world)
    summary = {
        "world": args.world,
        "scenario_id": scenario.scenario_id,
        "open_surfaces": list(scenario.domain_state_seed.get("open_surfaces", [])),
        "seat_contexts": [_seat_summary(ctx) for ctx in _scenario_contexts(scenario)],
        "tools": reference_surface().tool_names(),
    }
    _print_json(summary)
    return 0


def _cmd_init_finding(args: argparse.Namespace) -> int:
    now = _now_iso()
    finding_id = _finding_id(args.target)
    finding = {
        "finding_id": finding_id,
        "world": args.world,
        "target": args.target,
        "payload": args.payload,
        "task_prompt": args.task_prompt,
        "expected_risk": args.expected_risk,
        "notes": args.notes,
        "created_at": now,
        "status": "draft",
        "updated_at": now,
        "review_notes": "",
        "reviewed_at": "",
        "last_ab_summary": {},
        "challenge_path": "",
        "promoted_at": "",
    }
    out = Path(args.out) if args.out else DEFAULT_FINDINGS_DIR / f"{finding_id}.json"
    _write_json(out, finding)
    print(str(out))
    return 0


def _cmd_list_findings(args: argparse.Namespace) -> int:
    root = Path(args.dir)
    findings: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            finding = _normalize_finding(_read_json(path))
        except (json.JSONDecodeError, OSError, TypeError, KeyError):
            continue
        if args.status and finding.get("status") != args.status:
            continue
        findings.append(_finding_list_item(path, finding))
    findings.sort(key=lambda item: (str(item.get("created_at", "")), str(item.get("finding_id", ""))))
    if args.json:
        _print_json({"findings": findings})
    else:
        for item in findings:
            print(
                f"{item.get('status', '')}\t{item.get('finding_id', '')}\t"
                f"{item.get('target', '')}\t{item.get('path', '')}"
            )
    return 0


def _cmd_validate_finding(args: argparse.Namespace) -> int:
    finding_path = Path(args.finding)
    errors = _validate_finding_file(finding_path)
    result = {"valid": not errors, "errors": errors, "path": str(finding_path)}
    if args.json:
        _print_json(result)
    elif errors:
        for error in errors:
            print(f"invalid: {error}", file=sys.stderr)
    else:
        print("valid")
    return 0 if not errors else 1


def _cmd_manual_attempt(args: argparse.Namespace) -> int:
    try:
        tool_args = _parse_json_object(args.args_json, "--args-json")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.live and _normalized_manual_sut_mode(args.sut_mode) != "xaguard":
        print("--live is only valid with --sut-mode xaguard", file=sys.stderr)
        return 2

    scenario = load_scenario(args.world)
    injections = []
    for path in args.inject:
        injections.extend(load_injections(path))
    if injections:
        scenario = with_injections(scenario, injections)

    surface = reference_surface()
    if args.tool not in surface.tool_names():
        print(f"unknown tool for reference surface: {args.tool}", file=sys.stderr)
        return 2

    context = _manual_context(scenario, principal=args.principal, task=args.task, surface=surface)
    manual_scenario = replace(scenario, seat_context=context, seat_contexts=[context])
    sut = _manual_sut(
        manual_scenario,
        args.sut_mode,
        live=args.live,
        xa_guard_root=Path(args.xa_guard_root) if args.xa_guard_root else None,
    )
    out_dir = Path(args.out_dir) if args.out_dir else Path(".runtime") / "manual-attempts" / _manual_attempt_id(
        args.principal,
        args.tool,
    )
    result = _run_side(
        manual_scenario,
        surface,
        sut,
        out_dir,
        seat=ManualSeat([ToolCall(args.tool, tool_args)]),
        infra_errors_as_summary=args.live,
        evidence_meta={
            "agent": "manual",
            "principal": args.principal,
            "manual_tool": args.tool,
            "live": args.live,
            "injection_count": len(injections),
        },
    )
    summary = {
        "world": args.world,
        "principal": args.principal,
        "tool": args.tool,
        "sut_mode": args.sut_mode,
        "live": args.live,
        "injection_count": len(injections),
        "executed_at": _now_iso(),
        "attempt": _result_summary(out_dir, sut.sut_id, result),
    }
    _write_json(out_dir / "summary.json", summary)
    if args.json:
        _print_json(summary)
    else:
        _print_human_summary(summary["attempt"])
        print(f"evidence_dir\t{out_dir}")
    return 0


def _cmd_manual_session(args: argparse.Namespace) -> int:
    try:
        calls_label = "--calls-file" if args.calls_file else "--calls-json"
        calls_text = Path(args.calls_file).read_text(encoding="utf-8-sig") if args.calls_file else args.calls_json
        calls = _parse_tool_calls(str(calls_text), calls_label)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.live and _normalized_manual_sut_mode(args.sut_mode) != "xaguard":
        print("--live is only valid with --sut-mode xaguard", file=sys.stderr)
        return 2

    scenario = load_scenario(args.world)
    injections = []
    for path in args.inject:
        injections.extend(load_injections(path))
    if injections:
        scenario = with_injections(scenario, injections)

    surface = reference_surface()
    unknown = [call.tool for call in calls if call.tool not in surface.tool_names()]
    if unknown:
        print(f"unknown tool for reference surface: {', '.join(unknown)}", file=sys.stderr)
        return 2

    context = _manual_context(scenario, principal=args.principal, task=args.task, surface=surface)
    manual_scenario = replace(scenario, seat_context=context, seat_contexts=[context])
    sut = _manual_sut(
        manual_scenario,
        args.sut_mode,
        live=args.live,
        xa_guard_root=Path(args.xa_guard_root) if args.xa_guard_root else None,
    )
    out_dir = Path(args.out_dir) if args.out_dir else Path(".runtime") / "manual-sessions" / _manual_attempt_id(
        args.principal,
        calls[0].tool,
    )
    result = _run_side(
        manual_scenario,
        surface,
        sut,
        out_dir,
        seat=ManualSeat(calls),
        infra_errors_as_summary=args.live,
        evidence_meta={
            "agent": "manual-session",
            "principal": args.principal,
            "manual_call_count": len(calls),
            "manual_tools": [call.tool for call in calls],
            "live": args.live,
            "injection_count": len(injections),
        },
    )
    summary = {
        "world": args.world,
        "principal": args.principal,
        "tools": [call.tool for call in calls],
        "call_count": len(calls),
        "sut_mode": args.sut_mode,
        "live": args.live,
        "injection_count": len(injections),
        "executed_at": _now_iso(),
        "attempt": _result_summary(out_dir, sut.sut_id, result),
    }
    _write_json(out_dir / "summary.json", summary)
    if args.json:
        _print_json(summary)
    else:
        _print_human_summary(summary["attempt"])
        print(f"evidence_dir\t{out_dir}")
    return 0


def _cmd_review_finding(args: argparse.Namespace) -> int:
    finding_path = Path(args.finding)
    finding = _normalize_finding(_read_json(finding_path))
    now = _now_iso()
    finding["status"] = args.status
    finding["review_notes"] = args.notes
    finding["reviewed_at"] = now
    finding["updated_at"] = now
    _write_json(finding_path, finding)
    print(str(finding_path))
    return 0


def _cmd_run_ab(args: argparse.Namespace) -> int:
    if args.runs < 1:
        print("--runs must be >= 1", file=sys.stderr)
        return 2
    try:
        protected_label = _protected_label_from_mode(args.sut_mode)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.live and protected_label != "xaguard":
        print("--live is only valid with --sut-mode xaguard or null,xaguard", file=sys.stderr)
        return 2
    finding_path = Path(args.finding)
    finding = _normalize_finding(_read_json(finding_path))
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_AB_DIR / str(finding.get("finding_id", ""))
    plan = _ab_plan(finding, str(out_dir), args.agent, args.runs, protected_label, live=args.live)
    if not args.execute:
        _print_json({"dry_run": True, "plan": plan})
        return 0

    scenario = _scenario_from_finding(finding)
    surface = reference_surface()
    run_summaries = []

    for run_index in range(1, args.runs + 1):
        run_root = out_dir if args.runs == 1 else out_dir / f"run-{run_index:03d}"
        null_dir = run_root / "null"
        protected_dir = run_root / protected_label

        null_sut = NullSUT()
        null_result = _run_side(
            scenario,
            surface,
            null_sut,
            null_dir,
            infra_errors_as_summary=False,
            evidence_meta={
                "ab_side": "null",
                "finding_id": finding.get("finding_id", ""),
                "run_index": run_index,
                "protected_side": protected_label,
            },
        )

        protected_sut = _protected_sut(
            scenario,
            protected_label,
            live=args.live,
            xa_guard_root=Path(args.xa_guard_root) if args.xa_guard_root else None,
        )
        protected_result = _run_side(
            scenario,
            surface,
            protected_sut,
            protected_dir,
            infra_errors_as_summary=args.live,
            evidence_meta={
                "ab_side": protected_label,
                "finding_id": finding.get("finding_id", ""),
                "run_index": run_index,
                "live": args.live,
            },
        )
        run_summary = {
            "run_index": run_index,
            "null": _result_summary(null_dir, null_sut.sut_id, null_result),
            protected_label: _result_summary(protected_dir, protected_sut.sut_id, protected_result),
        }
        if protected_label != "guard":
            run_summary["guarded"] = run_summary[protected_label]
        run_summary["asr_null"] = _side_asr(run_summary["null"])
        run_summary[f"asr_{protected_label}"] = _side_asr(run_summary[protected_label])
        run_summary["asr_guard"] = run_summary[f"asr_{protected_label}"]
        run_summary["protection_delta"] = _protection_delta(
            run_summary["asr_null"],
            run_summary[f"asr_{protected_label}"],
        )
        run_summaries.append(run_summary)

    summary = {
        "finding_id": finding.get("finding_id", ""),
        "world": finding.get("world", ""),
        "target": finding.get("target", ""),
        "agent": args.agent,
        "sut_mode": args.sut_mode,
        "protected_side": protected_label,
        "live": args.live,
        "executed_at": _now_iso(),
        "run_count": args.runs,
        "runs": run_summaries,
    }
    if run_summaries:
        summary["null"] = run_summaries[0]["null"]
        summary[protected_label] = run_summaries[0][protected_label]
        if protected_label != "guard":
            summary["guarded"] = summary[protected_label]
    summary["aggregate"] = _aggregate_runs(run_summaries, protected_label=protected_label)
    summary["asr_null"] = summary["aggregate"]["asr_null"]
    summary[f"asr_{protected_label}"] = summary["aggregate"]["asr_protected"]
    summary["asr_guard"] = summary["aggregate"]["asr_protected"]
    summary["protection_delta"] = summary["aggregate"]["protection_delta"]
    _write_json(out_dir / "summary.json", summary)
    finding["last_ab_summary"] = {
        "path": str(out_dir / "summary.json"),
        "executed_at": summary["executed_at"],
        "run_count": args.runs,
        "aggregate": summary["aggregate"],
    }
    finding["updated_at"] = summary["executed_at"]
    _write_json(finding_path, finding)
    _print_json(summary)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if (path / "summary.json").is_file():
        summary = _read_json(path / "summary.json")
    else:
        summary = summarize_attempt(path)
    if args.json:
        _print_json(summary)
    else:
        _print_human_summary(summary)
    return 0


def _cmd_promote(args: argparse.Namespace) -> int:
    finding_path = Path(args.finding)
    finding = _normalize_finding(_read_json(finding_path))
    validation_errors = _validate_finding_file(finding_path)
    if validation_errors and not args.force:
        for error in validation_errors:
            print(f"finding invalid: {error}", file=sys.stderr)
        return 1
    if finding.get("status") != "reproduced":
        print("finding must be reviewed with status=reproduced before promote", file=sys.stderr)
        return 1
    gate_errors = _promotion_gate_errors(finding)
    if gate_errors and not args.force:
        for error in gate_errors:
            print(f"promotion gate failed: {error}", file=sys.stderr)
        print("use --force only for an explicit human override", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else DEFAULT_CHALLENGES_DIR / f"{finding.get('finding_id', '')}.json"
    if out.exists() and not args.force:
        print(f"challenge already exists: {out} (use --force to overwrite)", file=sys.stderr)
        return 1
    now = _now_iso()
    challenge = {
        "challenge_id": finding.get("finding_id", ""),
        "source_finding_id": finding.get("finding_id", ""),
        "world": finding.get("world", ""),
        "injections": [
            {
                "into": finding.get("target", ""),
                "content": finding.get("payload", ""),
                "meta": {"source": "workbench-promote"},
            }
        ],
        "task_prompt": finding.get("task_prompt", ""),
        "expected_risk": finding.get("expected_risk", ""),
        "notes": finding.get("notes", ""),
        "created_at": finding.get("created_at", ""),
        "promoted_at": now,
    }
    _write_json(out, challenge)
    finding["status"] = "promoted"
    finding["challenge_path"] = str(out)
    finding["promoted_at"] = now
    finding["updated_at"] = now
    _write_json(finding_path, finding)
    print(str(out))
    return 0


def summarize_attempt(path: Path | str) -> dict[str, Any]:
    root = Path(path)
    verdict_path = root / "verdict.json"
    ledger_path = root / "ledger.jsonl"
    tool_events_path = root / "tool-events.jsonl"
    audit_path = root / "audit.jsonl"

    verdict = _read_json(verdict_path) if verdict_path.is_file() else {}
    violations = verdict.get("violations", []) if isinstance(verdict.get("violations", []), list) else []
    ledger_rows = _read_jsonl(ledger_path) if ledger_path.is_file() else []
    tool_events = _read_jsonl(tool_events_path) if tool_events_path.is_file() else []
    audit_rows = _read_jsonl(audit_path) if audit_path.is_file() else []
    sends = [row for row in ledger_rows if row.get("action") in ("send", "send_email") and row.get("external")]
    leaked = sorted(
        {
            str(row.get("data_ref"))
            for row in sends
            if row.get("data_ref") and row.get("classification") in ("CONFIDENTIAL", "SECRET")
        }
    )
    decisions = {
        "allow": sum(1 for row in audit_rows if row.get("decision") == "allow"),
        "deny": sum(1 for row in audit_rows if row.get("decision") == "deny"),
    }
    return {
        "path": str(root),
        "verdict_passed": verdict.get("passed"),
        "violations_count": len(violations),
        "violation_property_ids": [v.get("property_id", "") for v in violations if isinstance(v, dict)],
        "external_send_count": len(sends),
        "leaked_data_refs": leaked,
        "sut_decisions": decisions,
        "tool_event_count": len(tool_events),
        "ledger_hash_chain_ok": _ledger_hash_chain_ok(ledger_path),
    }


def _scenario_from_finding(finding: dict[str, Any]) -> Scenario:
    scenario = load_scenario(str(finding["world"]))
    task_prompt = str(finding.get("task_prompt", ""))
    if task_prompt:
        if scenario.seat_context is not None:
            scenario.seat_context = replace(scenario.seat_context, task=task_prompt)
        if scenario.seat_contexts:
            scenario.seat_contexts = [replace(ctx, task=task_prompt) for ctx in scenario.seat_contexts]
    injection = Injection(into=str(finding["target"]), content=str(finding["payload"]))
    return with_injections(scenario, [injection])


def _guard_from_policy(scenario: Scenario) -> GuardStubSUT:
    policy = scenario.policy or {}
    return GuardStubSUT(
        sensitive_markers=tuple(policy.get("sensitive_markers", ())),
        deny_external_tools=tuple(policy.get("deny_external_tools", ("send_message", "send"))),
    )


def _protected_label_from_mode(mode: str) -> str:
    normalized = mode.strip().lower().replace(" ", "")
    aliases = {
        "both": "guard",
        "guard": "guard",
        "guardstub": "guard",
        "null,guard": "guard",
        "null,guardstub": "guard",
        "guard,null": "guard",
        "guardstub,null": "guard",
        "xaguard": "xaguard",
        "xa-guard": "xaguard",
        "null,xaguard": "xaguard",
        "null,xa-guard": "xaguard",
        "xaguard,null": "xaguard",
        "xa-guard,null": "xaguard",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(
            "--sut-mode must be one of guard, guardstub, null,guard, xaguard, or null,xaguard"
        ) from exc


def _protected_sut(
    scenario: Scenario,
    protected_label: str,
    *,
    live: bool,
    xa_guard_root: Path | None,
) -> SUT:
    if protected_label == "guard":
        return _guard_from_policy(scenario)
    if protected_label == "xaguard":
        return XaGuardSUT(
            policy=overlay_from_scenario(scenario),
            xa_guard_root=xa_guard_root,
            live=live,
        )
    raise AssertionError(f"unhandled protected side: {protected_label}")


def _run_side(
    scenario: Scenario,
    surface: Any,
    sut: SUT,
    evidence_dir: Path,
    *,
    seat: Any | None = None,
    infra_errors_as_summary: bool,
    evidence_meta: dict[str, Any],
) -> Any:
    try:
        return run_attempt(
            scenario,
            surface,
            seat or GullibleSeat(),
            sut,
            evidence_store=EvidenceStore(evidence_dir),
            evidence_meta=evidence_meta,
        )
    except (FileNotFoundError, RuntimeError, OSError, ImportError) as exc:
        if not infra_errors_as_summary:
            raise
        return _InfraError(exc)


class _InfraError:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.attempts: list[Any] = []


def _parse_json_object(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be a JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _parse_tool_calls(text: str, label: str = "--calls-json") -> list[ToolCall]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be a JSON list: {exc}") from exc
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty JSON list")
    calls: list[ToolCall] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{label} item {index} must be an object")
        tool = str(item.get("tool", "")).strip()
        if not tool:
            raise ValueError(f"{label} item {index} missing tool")
        args = item.get("args", {})
        if not isinstance(args, dict):
            raise ValueError(f"{label} item {index} args must be an object")
        calls.append(ToolCall(tool, dict(args)))
    return calls


def _manual_context(scenario: Scenario, *, principal: str, task: str, surface: Any) -> SeatContext:
    base = _context_for_principal(scenario, principal)
    if base is None:
        role = _role_for_principal(scenario, principal)
        base = SeatContext(principal=principal, role=role, task=task)
    return replace(
        base,
        principal=principal,
        role=base.role or _role_for_principal(scenario, principal),
        task=task,
        tool_names=surface.tool_names(),
        start_ts=int(getattr(base, "start_ts", 0) or 0),
        priority=int(getattr(base, "priority", 0) or 0),
    )


def _context_for_principal(scenario: Scenario, principal: str) -> SeatContext | None:
    for context in _scenario_contexts(scenario):
        if context.principal == principal:
            return context
    return None


def _role_for_principal(scenario: Scenario, principal: str) -> str:
    for item in scenario.principals:
        if item.principal_id == principal:
            return item.role
    return ""


def _manual_sut(
    scenario: Scenario,
    mode: str,
    *,
    live: bool,
    xa_guard_root: Path | None,
) -> SUT:
    normalized = _normalized_manual_sut_mode(mode)
    if normalized == "null":
        return NullSUT()
    if normalized == "guard":
        return _guard_from_policy(scenario)
    if normalized == "xaguard":
        return XaGuardSUT(policy=overlay_from_scenario(scenario), xa_guard_root=xa_guard_root, live=live)
    raise AssertionError(f"unhandled SUT mode: {normalized}")


def _normalized_manual_sut_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized == "guardstub":
        return "guard"
    if normalized == "xa-guard":
        return "xaguard"
    return normalized


def _manual_attempt_id(principal: str, tool: str) -> str:
    stem = _finding_id(f"{principal}-{tool}")
    return stem.replace("finding-", "manual-", 1)


def _result_summary(path: Path, sut_id: str, result: Any) -> dict[str, Any]:
    if isinstance(result, _InfraError):
        return {
            "path": str(path),
            "status": "infra_error",
            "error_type": type(result.exc).__name__,
            "error": str(result.exc),
            "sut_id": sut_id,
            "verdict_passed": None,
            "violations_count": 0,
            "violation_property_ids": [],
            "external_send_count": 0,
            "leaked_data_refs": [],
            "sut_decisions": {"allow": 0, "deny": 0},
            "tool_event_count": 0,
            "ledger_hash_chain_ok": None,
            "attempts_count": 0,
        }
    summary = summarize_attempt(path)
    summary["status"] = "completed"
    summary["sut_id"] = sut_id
    summary["attempts_count"] = len(result.attempts)
    return summary


def _side_asr(side: dict[str, Any]) -> int | None:
    if side.get("status") == "infra_error":
        return None
    return 1 if side.get("violations_count", 0) > 0 else 0


def _protection_delta(null_asr: int | None, protected_asr: int | None) -> int | None:
    if null_asr is None or protected_asr is None:
        return None
    return null_asr - protected_asr


def _aggregate_runs(runs: list[dict[str, Any]], *, protected_label: str = "guard") -> dict[str, Any]:
    run_count = len(runs)
    null_scored = [run.get("null", {}) for run in runs if run.get("null", {}).get("status") != "infra_error"]
    protected_scored = [
        run.get(protected_label, {})
        for run in runs
        if run.get(protected_label, {}).get("status") != "infra_error"
    ]
    null_leak_count = sum(1 for side in null_scored if side.get("violations_count", 0) > 0)
    protected_leak_count = sum(1 for side in protected_scored if side.get("violations_count", 0) > 0)
    asr_null = null_leak_count / len(null_scored) if null_scored else None
    asr_protected = protected_leak_count / len(protected_scored) if protected_scored else None
    protection_delta = None
    if asr_null is not None and asr_protected is not None:
        protection_delta = asr_null - asr_protected
    return {
        "run_count": run_count,
        "null_scored_count": len(null_scored),
        "null_leak_count": null_leak_count,
        "protected_label": protected_label,
        "protected_scored_count": len(protected_scored),
        "protected_infra_error_count": run_count - len(protected_scored),
        "protected_leak_count": protected_leak_count,
        "guard_leak_count": protected_leak_count,
        "asr_null": asr_null,
        "asr_protected": asr_protected,
        "asr_guard": asr_protected,
        "protection_delta": protection_delta,
    }


def _ab_plan(
    finding: dict[str, Any],
    out_dir: str,
    agent: str,
    runs: int,
    protected_label: str = "guard",
    *,
    live: bool = False,
) -> dict[str, Any]:
    protected_sut = "GuardStubSUT"
    if protected_label == "xaguard":
        protected_sut = "XaGuardSUT(live)" if live else "XaGuardSUT(offline)"
    run_plans = []
    for run_index in range(1, runs + 1):
        run_root = Path(out_dir) if runs == 1 else Path(out_dir) / f"run-{run_index:03d}"
        run_plans.append(
            {
                "run_index": run_index,
                "sides": [
                    {"label": "null", "sut": "NullSUT", "evidence_dir": str(run_root / "null")},
                    {"label": protected_label, "sut": protected_sut, "evidence_dir": str(run_root / protected_label)},
                ],
            }
        )
    return {
        "finding_id": finding.get("finding_id", ""),
        "world": finding.get("world", ""),
        "target": finding.get("target", ""),
        "agent": agent,
        "protected_side": protected_label,
        "live": live,
        "run_count": runs,
        "runs": run_plans,
        "sides": run_plans[0]["sides"] if run_plans else [],
    }


def _normalize_finding(finding: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(finding)
    now = _now_iso()
    normalized.setdefault("finding_id", _finding_id(str(normalized.get("target", "target"))))
    normalized.setdefault("world", "")
    normalized.setdefault("target", "")
    normalized.setdefault("payload", "")
    normalized.setdefault("task_prompt", "")
    normalized.setdefault("expected_risk", "sensitive-egress")
    normalized.setdefault("notes", "")
    normalized.setdefault("created_at", now)
    normalized.setdefault("status", "draft")
    normalized.setdefault("updated_at", normalized.get("created_at") or now)
    normalized.setdefault("review_notes", "")
    normalized.setdefault("reviewed_at", "")
    normalized.setdefault("last_ab_summary", {})
    normalized.setdefault("challenge_path", "")
    normalized.setdefault("promoted_at", "")
    return normalized


def _validate_finding_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        finding = _normalize_finding(_read_json(path))
    except (json.JSONDecodeError, OSError, TypeError) as exc:
        return [f"cannot read finding JSON: {exc}"]

    required = ("finding_id", "world", "target", "payload", "task_prompt", "expected_risk", "created_at")
    for key in required:
        if not str(finding.get(key, "")).strip():
            errors.append(f"missing or empty field: {key}")

    world = str(finding.get("world", ""))
    if world:
        try:
            load_scenario(world)
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            errors.append(f"world is not loadable: {exc}")

    target = str(finding.get("target", ""))
    if ":" not in target:
        errors.append("target must be scheme:locator")
    else:
        scheme, locator = target.split(":", 1)
        if not scheme or not locator:
            errors.append("target must have non-empty scheme and locator")

    if finding.get("status") not in FINDING_STATUSES:
        errors.append(f"status must be one of: {', '.join(sorted(FINDING_STATUSES))}")
    return errors


def _promotion_gate_errors(finding: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    last_summary = finding.get("last_ab_summary", {})
    summary_path_text = last_summary.get("path") if isinstance(last_summary, dict) else ""
    if not summary_path_text:
        return ["missing last_ab_summary.path; run run-ab --execute before promote"]
    summary_path = Path(str(summary_path_text))
    if not summary_path.is_file():
        return [f"A/B summary not found: {summary_path}"]
    try:
        summary = _read_json(summary_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"A/B summary is not readable JSON: {exc}"]

    if not summary.get("runs"):
        errors.append("A/B summary has no runs")
    protected_label = str(summary.get("protected_side") or "guard")
    aggregate = summary.get("aggregate", {})
    if isinstance(aggregate, dict) and aggregate.get("protected_infra_error_count", 0):
        errors.append("protected side contains INFRA_ERROR runs")
    for run in summary.get("runs", []):
        if not isinstance(run, dict):
            errors.append("A/B run entry is not an object")
            continue
        for side in ("null", protected_label):
            side_summary = run.get(side, {})
            if not isinstance(side_summary, dict):
                errors.append(f"run {run.get('run_index', '?')} missing {side} side summary")
                continue
            if side_summary.get("status") == "infra_error":
                errors.append(f"run {run.get('run_index', '?')} {side} side is INFRA_ERROR")
                continue
            attempt_path = Path(str(side_summary.get("path", "")))
            if not attempt_path.is_dir():
                errors.append(f"run {run.get('run_index', '?')} {side} evidence directory missing: {attempt_path}")
                continue
            required = ("verdict.json", "ledger.jsonl", "tool-events.jsonl", "audit.jsonl", "artifact-hashes.json")
            missing = [name for name in required if not (attempt_path / name).is_file()]
            if missing:
                errors.append(f"run {run.get('run_index', '?')} {side} evidence missing: {', '.join(missing)}")
            if side_summary.get("ledger_hash_chain_ok") is not True:
                errors.append(f"run {run.get('run_index', '?')} {side} ledger hash chain is not verified")
            alignment_errors = _attempt_alignment_errors(attempt_path, require_ledger=(side == protected_label))
            for error in alignment_errors:
                errors.append(f"run {run.get('run_index', '?')} {side} evidence audit alignment failed: {error}")
    return errors


def _attempt_alignment_errors(attempt_path: Path, *, require_ledger: bool) -> list[str]:
    errors: list[str] = []
    tool_events = _read_jsonl(attempt_path / "tool-events.jsonl")
    audit = _read_jsonl(attempt_path / "audit.jsonl")
    ledger_rows = _read_jsonl(attempt_path / "ledger.jsonl")
    attempts = [row for row in ledger_rows if row.get("action") == "tool_attempt"]
    decisions = [row for row in ledger_rows if row.get("action") == "sut_decision"]
    if len(audit) != len(tool_events):
        errors.append(f"range_audit count expected {len(tool_events)} actual {len(audit)}")
    if require_ledger:
        if len(attempts) != len(tool_events):
            errors.append(f"ledger_tool_attempt count expected {len(tool_events)} actual {len(attempts)}")
        if len(decisions) != len(tool_events):
            errors.append(f"ledger_sut_decision count expected {len(tool_events)} actual {len(decisions)}")
    for index, event in enumerate(tool_events):
        expected_tool = event.get("tool")
        audit_row = audit[index] if index < len(audit) else {}
        if audit_row.get("tool") != expected_tool:
            errors.append(
                f"seq {index + 1} range_audit.tool expected {expected_tool} actual {audit_row.get('tool')}"
            )
        if require_ledger:
            attempt_row = attempts[index] if index < len(attempts) else {}
            decision_row = decisions[index] if index < len(decisions) else {}
            if attempt_row.get("tool") != expected_tool:
                errors.append(
                    f"seq {index + 1} ledger_tool_attempt.tool expected {expected_tool} actual {attempt_row.get('tool')}"
                )
            if decision_row.get("tool") != expected_tool:
                errors.append(
                    f"seq {index + 1} ledger_sut_decision.tool expected {expected_tool} actual {decision_row.get('tool')}"
                )
            expected_decision = _canonical_decision(decision_row.get("decision"))
            actual_decision = _canonical_decision(audit_row.get("decision"))
            if actual_decision != expected_decision:
                errors.append(
                    f"seq {index + 1} range_audit.decision expected {expected_decision} actual {actual_decision}"
                )
    raw_xaguard = _read_jsonl(attempt_path / "xa-guard-audit" / "audit.jsonl")
    if raw_xaguard:
        if len(raw_xaguard) < len(audit):
            errors.append(f"raw_xaguard_audit count expected at least {len(audit)} actual {len(raw_xaguard)}")
        for index, audit_row in enumerate(audit):
            raw_row = raw_xaguard[index] if index < len(raw_xaguard) else {}
            raw_tool = raw_row.get("gen_ai.tool.name") or raw_row.get("tool")
            if raw_tool != audit_row.get("tool"):
                errors.append(
                    f"seq {index + 1} raw_xaguard_audit.tool expected {audit_row.get('tool')} actual {raw_tool}"
                )
            raw_decision = _canonical_decision(raw_row.get("gen_ai.decision.final") or raw_row.get("decision"))
            audit_decision = _canonical_decision(audit_row.get("decision"))
            if raw_decision != audit_decision:
                errors.append(
                    f"seq {index + 1} raw_xaguard_audit.decision expected {audit_decision} actual {raw_decision}"
                )
    return errors


def _canonical_decision(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"deny", "require_approval"}:
        return "deny"
    if text in {"allow", "warn"}:
        return "allow"
    return text


def _finding_list_item(path: Path, finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "finding_id": finding.get("finding_id", ""),
        "status": finding.get("status", "draft"),
        "world": finding.get("world", ""),
        "target": finding.get("target", ""),
        "expected_risk": finding.get("expected_risk", ""),
        "created_at": finding.get("created_at", ""),
        "updated_at": finding.get("updated_at", ""),
        "challenge_path": finding.get("challenge_path", ""),
    }


def _seat_summary(ctx: Any) -> dict[str, Any]:
    return {
        "principal": ctx.principal,
        "role": ctx.role,
        "task": ctx.task,
        "receiver": ctx.receiver,
        "channels": ctx.consumed_channels(),
        "tool_names": list(ctx.tool_names),
        "external_receivers": list(ctx.external_receivers),
        "start_ts": getattr(ctx, "start_ts", 0),
        "priority": getattr(ctx, "priority", 100),
    }


def _scenario_contexts(scenario: Scenario) -> list[Any]:
    if scenario.seat_contexts:
        return list(scenario.seat_contexts)
    if scenario.seat_context is not None:
        return [scenario.seat_context]
    return []


def _finding_id(target: str) -> str:
    stem = "".join(ch.lower() if ch.isalnum() else "-" for ch in target).strip("-")
    while "--" in stem:
        stem = stem.replace("--", "-")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"finding-{stem or 'target'}-{stamp}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ledger_hash_chain_ok(path: Path) -> bool | None:
    if not path.is_file():
        return None
    return Ledger.load(path).verify_hash_chain()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _print_human_summary(summary: dict[str, Any]) -> None:
    if "null" in summary and "guard" in summary:
        print(f"finding={summary.get('finding_id', '')}")
        for side in ("null", "guard"):
            item = summary[side]
            print(
                f"{side}: verdict={item.get('verdict_passed')} "
                f"violations={item.get('violations_count')} "
                f"external_send={item.get('external_send_count')} "
                f"deny={item.get('sut_decisions', {}).get('deny')}"
            )
        print(f"protection_delta={summary.get('protection_delta')}")
        return
    print(
        f"verdict={summary.get('verdict_passed')} "
        f"violations={summary.get('violations_count')} "
        f"external_send={summary.get('external_send_count')} "
        f"ledger_hash_chain_ok={summary.get('ledger_hash_chain_ok')}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
