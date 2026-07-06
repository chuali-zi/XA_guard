"""Product CLI for Open Agent Range.

This module provides the SP7-facing command shape:

- ``day`` runs a world through Seat/SUT and writes a standard evidence package.
- ``replay`` verifies an evidence package from ledger/hash/audit artifacts.
- ``report`` renders an evidence package as JSON, Markdown, or HTML.

It intentionally reuses the kernel runner instead of inventing a parallel path.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from kernel.demo import build_seat, reference_surface
from kernel.evidence import HASH_MANIFEST, EvidenceStore
from kernel.ledger import Ledger
from kernel.policy_overlay import overlay_from_scenario
from kernel.run import run_attempt
from kernel.scenario import build_world, load_injections, load_scenario, with_injections
from kernel.sut import GuardStubSUT, NullSUT, SUT, ToolCall, XaGuardSUT
from kernel.world import World

WORKBENCH_ALIASES = {
    "worlds",
    "surfaces",
    "init-finding",
    "list-findings",
    "validate-finding",
    "manual-attempt",
    "review-finding",
    "run-ab",
    "show",
    "promote",
}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if argv and argv[0] in WORKBENCH_ALIASES:
        from kernel import workbench

        return workbench.main(argv)

    parser = argparse.ArgumentParser(description="Open Agent Range product CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    day = sub.add_parser("day", help="run a scenario day and write evidence")
    day.add_argument("--world", required=True)
    day.add_argument("--agent", choices=["scripted", "gullible", "opencode"], default="scripted")
    day.add_argument("--sut", choices=["null", "guard", "guardstub", "xaguard", "xa-guard"], default="null")
    day.add_argument("--model", default="deepseek/deepseek-v4-flash")
    day.add_argument("--opencode-agent", default="build")
    day.add_argument("--opencode-multiround", action="store_true")
    day.add_argument("--timeout", type=int, default=120)
    day.add_argument("--inject", action="append", default=[])
    day.add_argument("--repeat", type=int, default=1)
    day.add_argument("--evidence-dir", required=True)
    day.add_argument("--live", action="store_true", help="use live XA-Guard when --sut xaguard")
    day.add_argument("--xa-guard-root", help="path to external XA-Guard repository for live mode")

    replay = sub.add_parser("replay", help="verify an attempt evidence directory")
    replay.add_argument("--attempt", required=True)
    replay.add_argument("--verify-hashes", action="store_true")
    replay.add_argument("--verify-ledger", action="store_true")
    replay.add_argument("--verify-sut-audit", action="store_true")
    replay.add_argument("--json", action="store_true")

    report = sub.add_parser("report", help="render an attempt evidence report")
    report.add_argument("--run", required=True)
    report.add_argument("--format", choices=["json", "md", "html"], default="json")
    report.add_argument("--out")

    sut = sub.add_parser("sut", help="SUT product checks")
    sut_sub = sut.add_subparsers(dest="sut_command", required=True)
    sut_check = sut_sub.add_parser("check", help="check SUT configuration and optional live availability")
    sut_check.add_argument("--sut", choices=["null", "guard", "guardstub", "xaguard", "xa-guard"], required=True)
    sut_check.add_argument("--world", required=True)
    sut_check.add_argument("--live", action="store_true", help="perform a live XA-Guard smoke call")
    sut_check.add_argument("--xa-guard-root", help="path to external XA-Guard repository for live mode")
    sut_check.add_argument("--json", action="store_true")

    workbench = sub.add_parser("workbench", help="red-team workbench product surface")
    workbench_sub = workbench.add_subparsers(dest="workbench_command", required=True)
    serve = workbench_sub.add_parser("serve", help="write and optionally serve the workbench dashboard")
    serve.add_argument("--world", required=True)
    serve.add_argument("--findings-dir", default=str(Path(".runtime") / "findings"))
    serve.add_argument("--out-dir", default=str(Path(".runtime") / "workbench"))
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-server", action="store_true", help="write static files and exit")
    serve.add_argument("--json", action="store_true", help="emit JSON metadata")

    args = parser.parse_args(argv)
    if args.command == "day":
        return _cmd_day(args)
    if args.command == "replay":
        return _cmd_replay(args)
    if args.command == "report":
        return _cmd_report(args)
    if args.command == "sut" and args.sut_command == "check":
        return _cmd_sut_check(args)
    if args.command == "workbench" and args.workbench_command == "serve":
        return _cmd_workbench_serve(args)
    raise AssertionError(f"unhandled command: {args.command}")


def _cmd_day(args: argparse.Namespace) -> int:
    if args.repeat < 1:
        print("--repeat must be >= 1", file=sys.stderr)
        return 2
    if args.live and _normalize_sut(args.sut) != "xaguard":
        print("--live is only valid with --sut xaguard", file=sys.stderr)
        return 2

    base = load_scenario(args.world)
    injections = []
    for path in args.inject:
        injections.extend(load_injections(path))
    scenario = with_injections(base, injections) if injections else base
    surface = reference_surface()
    out_root = Path(args.evidence_dir)
    runs: list[dict[str, Any]] = []

    for run_index in range(1, args.repeat + 1):
        attempt_dir = out_root if args.repeat == 1 else out_root / f"run-{run_index:03d}"
        sut = _sut_for(args.sut, scenario, live=args.live, xa_guard_root=args.xa_guard_root)
        seat_args = SimpleNamespace(
            agent=args.agent,
            model=args.model,
            timeout=args.timeout,
            opencode_agent=args.opencode_agent,
            opencode_multiround=args.opencode_multiround,
        )
        result = run_attempt(
            scenario,
            surface,
            build_seat(seat_args, scenario),
            sut,
            evidence_store=EvidenceStore(attempt_dir),
            evidence_meta={
                "product_command": "day",
                "agent": args.agent,
                "model": args.model if args.agent == "opencode" else "",
                "sut": _normalize_sut(args.sut),
                "live": args.live,
                "run_index": run_index,
                "injection_count": len(injections),
            },
        )
        runs.append(
            {
                "run_index": run_index,
                "attempt_dir": str(attempt_dir),
                "verdict_passed": result.verdict.passed,
                "violation_count": len(result.violations),
                "ledger_hash_chain_ok": result.ledger.verify_hash_chain(),
                "ledger_entries": len(result.ledger.entries),
            }
        )

    summary = {
        "world": args.world,
        "agent": args.agent,
        "sut": _normalize_sut(args.sut),
        "live": args.live,
        "repeat": args.repeat,
        "injection_count": len(injections),
        "executed_at": _now_iso(),
        "runs": runs,
        "all_passed": all(run["verdict_passed"] for run in runs),
        "total_violations": sum(int(run["violation_count"]) for run in runs),
    }
    _write_json(out_root / "day-summary.json", summary)
    _print_json(summary)
    return 0 if summary["total_violations"] == 0 else 1


def _cmd_replay(args: argparse.Namespace) -> int:
    attempt = Path(args.attempt)
    result = verify_attempt(
        attempt,
        verify_hashes=args.verify_hashes,
        verify_ledger=args.verify_ledger,
        verify_sut_audit=args.verify_sut_audit,
    )
    if args.json:
        _print_json(result.to_dict())
    else:
        print(_render_replay_text(result))
    return 0 if result.ok else 1


def _cmd_report(args: argparse.Namespace) -> int:
    report = build_report(Path(args.run))
    if args.format == "json":
        text = json.dumps(report, ensure_ascii=False, indent=2)
    elif args.format == "md":
        text = render_markdown_report(report)
    else:
        text = render_html_report(report)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text)
    return 0


def _cmd_sut_check(args: argparse.Namespace) -> int:
    if args.live and _normalize_sut(args.sut) != "xaguard":
        print("--live is only valid with --sut xaguard", file=sys.stderr)
        return 2
    scenario = load_scenario(args.world)
    surface = reference_surface()
    result: dict[str, Any] = {
        "ok": True,
        "sut": _normalize_sut(args.sut),
        "world": args.world,
        "scenario_id": scenario.scenario_id,
        "live": args.live,
        "tool_count": len(surface.tools),
        "bound_properties": list(scenario.bound_properties),
        "policy_overlay": {
            "sensitive_markers": list((scenario.policy or {}).get("sensitive_markers", [])),
            "deny_external_tools": list((scenario.policy or {}).get("deny_external_tools", [])),
        },
        "smoke": {},
    }
    sut = _sut_for(args.sut, scenario, live=args.live, xa_guard_root=args.xa_guard_root)
    if args.live:
        world = build_world(scenario)
        ledger = Ledger()
        try:
            output = sut.invoke(
                world,
                ledger,
                scenario.principals[0].principal_id if scenario.principals else "synthetic-checker",
                ToolCall("read_policy", {"locator": "agent-handbook"}),
                surface,
            )
            result["smoke"] = {
                "ok": True,
                "tool": "read_policy",
                "decision": output.get("decision", "allow"),
                "audit_count": len(sut.audit),
                "ledger_hash_chain_ok": ledger.verify_hash_chain(),
            }
        except Exception as exc:  # live external SUT availability check
            result["ok"] = False
            result["smoke"] = {"ok": False, "status": "INFRA_ERROR", "error": str(exc)}
    else:
        result["smoke"] = {
            "ok": True,
            "mode": "offline-config",
            "sut_id": sut.sut_id,
            "surface_tools": surface.tool_names(),
        }
    if args.json:
        _print_json(result)
    else:
        print(f"sut\t{result['sut']}")
        print(f"scenario\t{result['scenario_id']}")
        print(f"ok\t{result['ok']}")
        if result.get("smoke"):
            print(f"smoke\t{result['smoke'].get('status') or result['smoke'].get('mode') or result['smoke'].get('decision')}")
    return 0 if result["ok"] else 1


def _cmd_workbench_serve(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state = build_workbench_state(Path(args.world), Path(args.findings_dir), out_dir)
    _write_json(out_dir / "workbench-state.json", state)
    (out_dir / "index.html").write_text(render_workbench_html(state), encoding="utf-8", newline="\n")

    url = f"http://{args.host}:{args.port}/"
    result = {"ok": True, "url": url, "out_dir": str(out_dir), "files": ["index.html", "workbench-state.json"]}
    if args.no_server:
        if args.json:
            _print_json(result)
        else:
            print(str(out_dir / "index.html"))
        return 0

    if args.json:
        _print_json(result)
    else:
        print(f"Serving Open Agent Range workbench at {url}")
    handler = http.server.SimpleHTTPRequestHandler
    with _pushd(out_dir):
        with socketserver.TCPServer((args.host, args.port), handler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                return 0
    return 0


@dataclass
class ReplayCheckResult:
    attempt_dir: str
    ok: bool
    checks: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"attempt_dir": self.attempt_dir, "ok": self.ok, "checks": self.checks}


def verify_attempt(
    attempt: Path,
    *,
    verify_hashes: bool,
    verify_ledger: bool,
    verify_sut_audit: bool,
) -> ReplayCheckResult:
    checks: dict[str, Any] = {}
    if verify_hashes:
        checks["artifact_hashes"] = _verify_artifact_hashes(attempt)
    if verify_ledger:
        ledger_path = attempt / "ledger.jsonl"
        if ledger_path.is_file():
            ledger = Ledger.load(ledger_path)
            projection = ledger.replay(World())
            expected_path = attempt / "ledger-replay.json"
            expected = _read_json(expected_path) if expected_path.is_file() else {}
            checks["ledger"] = {
                "ok": ledger.verify_hash_chain() and (not expected or expected == projection),
                "hash_chain_ok": ledger.verify_hash_chain(),
                "projection_matches_artifact": not expected or expected == projection,
                "entry_count": len(ledger.entries),
            }
        else:
            checks["ledger"] = {"ok": False, "error": "missing ledger.jsonl"}
    if verify_sut_audit:
        checks["sut_audit"] = _verify_sut_audit(attempt)
    ok = all(bool(value.get("ok")) for value in checks.values()) if checks else True
    return ReplayCheckResult(attempt_dir=str(attempt), ok=ok, checks=checks)


def build_report(run_dir: Path) -> dict[str, Any]:
    manifest = _read_json(run_dir / "run-manifest.json") if (run_dir / "run-manifest.json").is_file() else {}
    verdict = _read_json(run_dir / "verdict.json") if (run_dir / "verdict.json").is_file() else {}
    replay = _read_json(run_dir / "ledger-replay.json") if (run_dir / "ledger-replay.json").is_file() else {}
    accountability = (
        _read_json(run_dir / "accountability-report.json")
        if (run_dir / "accountability-report.json").is_file()
        else {}
    )
    hashes = _read_json(run_dir / HASH_MANIFEST) if (run_dir / HASH_MANIFEST).is_file() else {}
    tool_events = _read_jsonl(run_dir / "tool-events.jsonl")
    timeline = _read_jsonl(run_dir / "timeline.jsonl")
    audit = _read_jsonl(run_dir / "audit.jsonl")
    violations = verdict.get("violations", []) if isinstance(verdict.get("violations", []), list) else []
    return {
        "run_dir": str(run_dir),
        "scenario_id": manifest.get("scenario_id", ""),
        "seat_id": manifest.get("seat_id", ""),
        "sut_id": manifest.get("sut_id", ""),
        "verdict_passed": verdict.get("passed"),
        "violation_count": len(violations),
        "violation_property_ids": [item.get("property_id", "") for item in violations if isinstance(item, dict)],
        "ledger_hash_chain_ok": replay.get("hash_chain_ok"),
        "ledger_entry_count": replay.get("entry_count"),
        "tool_event_count": len(tool_events),
        "timeline_rows": len(timeline),
        "sut_audit_count": len(audit),
        "accountability": {
            "violation_count": accountability.get("violation_count", 0),
            "all_violations_accountable": accountability.get("all_violations_accountable"),
        },
        "artifact_count": len(hashes),
        "artifacts": sorted(hashes.keys()),
    }


def build_workbench_state(world_path: Path, findings_dir: Path, out_dir: Path) -> dict[str, Any]:
    scenario = load_scenario(world_path)
    surface = reference_surface()
    findings = _load_finding_items(findings_dir)
    contexts = scenario.seat_contexts or ([scenario.seat_context] if scenario.seat_context else [])
    return {
        "generated_at": _now_iso(),
        "world_path": str(world_path),
        "scenario_id": scenario.scenario_id,
        "dashboard_dir": str(out_dir),
        "principals": [
            {"principal_id": item.principal_id, "role": item.role, "domain": item.domain}
            for item in scenario.principals
        ],
        "seat_contexts": [
            {
                "principal": ctx.principal,
                "role": ctx.role,
                "task": ctx.task,
                "start_ts": ctx.start_ts,
                "priority": ctx.priority,
                "tool_names": list(ctx.tool_names),
                "channels": _context_channels(ctx),
            }
            for ctx in contexts
        ],
        "open_surfaces": list(scenario.domain_state_seed.get("open_surfaces", [])),
        "bound_properties": list(scenario.bound_properties),
        "scheduled_event_count": len(scenario.scheduled_events),
        "normal_event_count": len(scenario.normal_events),
        "tools": [
            {
                "name": tool.name,
                "risk_level": tool.risk_level,
                "capabilities": list(tool.capabilities),
                "input_max_taint": tool.input_max_taint,
                "output_taint": tool.output_taint,
                "description": tool.description,
            }
            for tool in surface.tools
        ],
        "findings_dir": str(findings_dir),
        "findings": findings,
        "commands": {
            "day_null": f"python -m kernel.range_cli day --world {world_path} --sut null --evidence-dir .runtime/day-null",
            "day_xaguard": f"python -m kernel.range_cli day --world {world_path} --sut xaguard --evidence-dir .runtime/day-xaguard",
            "manual_attempt": f"python -m kernel.range_cli manual-attempt --world {world_path} --principal <seat> --tool <tool> --args-json '{{}}'",
            "run_ab": "python -m kernel.range_cli run-ab --finding <finding.json> --sut-mode null,xaguard --repeat 3 --live --execute",
            "report": "python -m kernel.range_cli report --run <attempt-dir> --format html --out report.html",
            "replay": "python -m kernel.range_cli replay --attempt <attempt-dir> --verify-hashes --verify-ledger --verify-sut-audit",
        },
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Open Agent Range Report",
        "",
        f"- Run: `{report['run_dir']}`",
        f"- Scenario: `{report.get('scenario_id', '')}`",
        f"- Seat: `{report.get('seat_id', '')}`",
        f"- SUT: `{report.get('sut_id', '')}`",
        f"- Verdict passed: `{report.get('verdict_passed')}`",
        f"- Violations: `{report.get('violation_count')}`",
        f"- Ledger hash chain OK: `{report.get('ledger_hash_chain_ok')}`",
        f"- Tool events: `{report.get('tool_event_count')}`",
        f"- SUT audit rows: `{report.get('sut_audit_count')}`",
        f"- Artifacts: `{report.get('artifact_count')}`",
    ]
    if report.get("violation_property_ids"):
        lines.extend(["", "## Violations", ""])
        lines.extend(f"- `{item}`" for item in report["violation_property_ids"])
    return "\n".join(lines) + "\n"


def render_html_report(report: dict[str, Any]) -> str:
    rows = [
        ("Run", report.get("run_dir", "")),
        ("Scenario", report.get("scenario_id", "")),
        ("Seat", report.get("seat_id", "")),
        ("SUT", report.get("sut_id", "")),
        ("Verdict passed", report.get("verdict_passed")),
        ("Violations", report.get("violation_count")),
        ("Ledger hash chain OK", report.get("ledger_hash_chain_ok")),
        ("Tool events", report.get("tool_event_count")),
        ("SUT audit rows", report.get("sut_audit_count")),
        ("Artifacts", report.get("artifact_count")),
    ]
    body = "\n".join(
        f"<tr><th>{_html(str(key))}</th><td>{_html(str(value))}</td></tr>" for key, value in rows
    )
    return (
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\"><title>Open Agent Range Report</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:32px;line-height:1.4}"
        "table{border-collapse:collapse}th,td{border:1px solid #ccc;padding:6px 10px;text-align:left}"
        "th{background:#f5f5f5}</style></head><body>"
        "<h1>Open Agent Range Report</h1><table>"
        f"{body}"
        "</table></body></html>\n"
    )


def render_workbench_html(state: dict[str, Any]) -> str:
    metric_rows = [
        ("Scenario", state.get("scenario_id", "")),
        ("Principals", len(state.get("principals", []))),
        ("Seats", len(state.get("seat_contexts", []))),
        ("Open surfaces", len(state.get("open_surfaces", []))),
        ("Properties", len(state.get("bound_properties", []))),
        ("Tools", len(state.get("tools", []))),
        ("Findings", len(state.get("findings", []))),
    ]
    metrics = "".join(
        f"<div class=\"metric\"><span>{_html(str(label))}</span><strong>{_html(str(value))}</strong></div>"
        for label, value in metric_rows
    )
    seats = "".join(
        "<tr>"
        f"<td>{_html(str(item.get('principal', '')))}</td>"
        f"<td>{_html(str(item.get('role', '')))}</td>"
        f"<td>{_html(', '.join(item.get('tool_names', [])))}</td>"
        f"<td>{_html(', '.join(item.get('channels', [])))}</td>"
        "</tr>"
        for item in state.get("seat_contexts", [])
    )
    surfaces = "".join(f"<li>{_html(str(item))}</li>" for item in state.get("open_surfaces", []))
    properties = "".join(f"<li>{_html(str(item))}</li>" for item in state.get("bound_properties", []))
    findings = "".join(
        "<tr>"
        f"<td>{_html(str(item.get('status', '')))}</td>"
        f"<td>{_html(str(item.get('finding_id', '')))}</td>"
        f"<td>{_html(str(item.get('target', '')))}</td>"
        f"<td>{_html(str(item.get('path', '')))}</td>"
        "</tr>"
        for item in state.get("findings", [])
    )
    commands = "".join(
        f"<tr><th>{_html(str(name))}</th><td><code>{_html(str(command))}</code></td></tr>"
        for name, command in state.get("commands", {}).items()
    )
    return (
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\"><title>Open Agent Range Workbench</title>"
        "<style>"
        ":root{color-scheme:light;background:#f7f7f4;color:#171716}"
        "body{font-family:Inter,Segoe UI,system-ui,sans-serif;margin:0;line-height:1.45}"
        "header{background:#17201b;color:#fff;padding:28px 36px}"
        "main{padding:28px 36px;max-width:1180px;margin:auto}"
        "h1{font-size:30px;margin:0 0 8px}h2{font-size:18px;margin:28px 0 12px}"
        ".sub{color:#cbd8d0;margin:0}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:18px 0}"
        ".metric{background:#fff;border:1px solid #d8d8d2;padding:12px}.metric span{display:block;color:#686861;font-size:12px}.metric strong{font-size:20px}"
        "table{border-collapse:collapse;width:100%;background:#fff}th,td{border:1px solid #d8d8d2;padding:8px 10px;text-align:left;vertical-align:top}"
        "th{background:#ecece6}ul{columns:2;background:#fff;border:1px solid #d8d8d2;padding:14px 28px}code{white-space:pre-wrap}"
        "</style></head><body>"
        "<header><h1>Open Agent Range Workbench</h1>"
        f"<p class=\"sub\">{_html(str(state.get('world_path', '')))}</p></header><main>"
        f"<section class=\"metrics\">{metrics}</section>"
        "<h2>Seats</h2><table><tr><th>Principal</th><th>Role</th><th>Tools</th><th>Channels</th></tr>"
        f"{seats}</table>"
        "<h2>Open Injection Surfaces</h2><ul>"
        f"{surfaces}</ul>"
        "<h2>Bound Properties</h2><ul>"
        f"{properties}</ul>"
        "<h2>Finding Queue</h2><table><tr><th>Status</th><th>ID</th><th>Target</th><th>Path</th></tr>"
        f"{findings}</table>"
        "<h2>Executable Commands</h2><table>"
        f"{commands}</table>"
        "</main></body></html>\n"
    )


def _sut_for(mode: str, scenario: Any, *, live: bool, xa_guard_root: str | None) -> SUT:
    normalized = _normalize_sut(mode)
    if normalized == "null":
        return NullSUT()
    if normalized == "guard":
        policy = scenario.policy or {}
        return GuardStubSUT(
            sensitive_markers=tuple(policy.get("sensitive_markers", ())),
            deny_external_tools=tuple(policy.get("deny_external_tools", ("send_message", "send"))),
        )
    if normalized == "xaguard":
        return XaGuardSUT(
            policy=overlay_from_scenario(scenario),
            xa_guard_root=Path(xa_guard_root) if xa_guard_root else None,
            live=live,
        )
    raise AssertionError(f"unhandled sut mode: {normalized}")


def _normalize_sut(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized == "guardstub":
        return "guard"
    if normalized == "xa-guard":
        return "xaguard"
    return normalized


def _verify_artifact_hashes(attempt: Path) -> dict[str, Any]:
    manifest_path = attempt / HASH_MANIFEST
    if not manifest_path.is_file():
        return {"ok": False, "error": f"missing {HASH_MANIFEST}"}
    manifest = _read_json(manifest_path)
    mismatches: list[str] = []
    missing: list[str] = []
    for name, expected in manifest.items():
        path = attempt / name
        if not path.is_file():
            missing.append(name)
            continue
        from hashlib import sha256

        actual = sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append(name)
    return {
        "ok": not missing and not mismatches,
        "checked": len(manifest),
        "missing": missing,
        "mismatches": mismatches,
    }


def _verify_sut_audit(attempt: Path) -> dict[str, Any]:
    tool_events = _read_jsonl(attempt / "tool-events.jsonl")
    audit = _read_jsonl(attempt / "audit.jsonl")
    decisions = [row for row in _read_jsonl(attempt / "ledger.jsonl") if row.get("action") == "sut_decision"]
    audit_tools = [row.get("tool") for row in audit]
    event_tools = [row.get("tool") for row in tool_events]
    ok = len(audit) == len(tool_events) and (not decisions or len(decisions) == len(tool_events))
    return {
        "ok": ok,
        "tool_event_count": len(tool_events),
        "audit_count": len(audit),
        "ledger_sut_decision_count": len(decisions),
        "audit_tools": audit_tools,
        "tool_event_tools": event_tools,
    }


def _render_replay_text(result: ReplayCheckResult) -> str:
    lines = [f"attempt\t{result.attempt_dir}", f"ok\t{result.ok}"]
    for name, check in result.checks.items():
        lines.append(f"{name}\t{check.get('ok')}")
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _load_finding_items(findings_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not findings_dir.is_dir():
        return items
    for path in sorted(findings_dir.glob("*.json")):
        try:
            finding = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        items.append(
            {
                "path": str(path),
                "finding_id": finding.get("finding_id", path.stem),
                "status": finding.get("status", "draft"),
                "world": finding.get("world", ""),
                "target": finding.get("target", ""),
                "expected_risk": finding.get("expected_risk", ""),
                "updated_at": finding.get("updated_at", ""),
            }
        )
    return items


def _context_channels(ctx: Any) -> list[str]:
    channels = ctx.consumed_channels() if hasattr(ctx, "consumed_channels") else {}
    return [f"{scheme}:{locator}" if locator else str(scheme) for scheme, locator in sorted(channels.items())]


class _pushd:
    def __init__(self, target: Path) -> None:
        self.target = target
        self.previous: str | None = None

    def __enter__(self) -> None:
        self.previous = os.getcwd()
        os.chdir(self.target)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.previous is not None:
            os.chdir(self.previous)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
