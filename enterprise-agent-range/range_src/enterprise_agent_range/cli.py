from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .fixtures import load_manifest
from .protocol import build_protocol_state, replay_ide_file, serve_http, serve_stdio
from .reports import compare_run_outputs
from .runner import run_cases
from .tools import TOOL_DEFINITIONS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="enterprise-agent-range")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a case manifest")
    validate.add_argument("--manifest", default="cases/p0_manifest.json", type=Path)

    run = subparsers.add_parser("run", help="run a case manifest")
    run.add_argument("--manifest", default="cases/p0_manifest.json", type=Path)
    run.add_argument("--out", default="reports", type=Path)
    run.add_argument("--adapter", default="null_adapter")
    run.add_argument("--sut-id", default="null-baseline")
    run.add_argument("--mode", default="local")
    run.add_argument("--operator", default="local")
    run.add_argument("--seed", default=20260701, type=int)
    run.add_argument("--run-id", default=None)

    compare = subparsers.add_parser("compare", help="compare two run output directories")
    compare.add_argument("--baseline", required=True, type=Path)
    compare.add_argument("--candidate", required=True, type=Path)
    compare.add_argument("--out", required=True, type=Path)

    subparsers.add_parser("tools", help="print tool surface definitions")

    p2_status = subparsers.add_parser("p2-status", help="print P2 capability scaffold registry")
    p2_status.add_argument("--json", action="store_true", help="emit JSON instead of a table")

    stdio = subparsers.add_parser("serve-stdio", help="serve MCP-like JSON-lines protocol on stdio")
    stdio.add_argument("--manifest-root", default=Path.cwd(), type=Path)
    stdio.add_argument("--run-id", default="stdio-local")
    stdio.add_argument("--sut-id", default="local-protocol")

    http = subparsers.add_parser("serve-http", help="serve MCP-like local HTTP protocol")
    http.add_argument("--host", default="127.0.0.1")
    http.add_argument("--port", default=8765, type=int)
    http.add_argument("--manifest-root", default=Path.cwd(), type=Path)
    http.add_argument("--run-id", default="http-local")
    http.add_argument("--sut-id", default="local-protocol")

    replay = subparsers.add_parser("ide-replay", help="replay local simulated IDE tool calls")
    replay.add_argument("replay_file", type=Path)
    replay.add_argument("--manifest-root", default=Path.cwd(), type=Path)
    replay.add_argument("--run-id", default="ide-replay-local")
    replay.add_argument("--sut-id", default="local-protocol")

    arena_live = subparsers.add_parser("arena-live", help="run the live arena office/mail vertical slice")
    arena_live.add_argument("--challenge", action="append", type=Path, default=None)
    arena_live.add_argument("--suite", default=None, type=Path)
    arena_live.add_argument("--sut-mode", choices=["guard", "null", "both"], default="both")
    arena_live.add_argument("--repeat", default=1, type=int)
    arena_live.add_argument("--out", default=Path("reports"), type=Path)
    arena_live.add_argument("--run-id", default=None)
    arena_live.add_argument("--model", default="opencode-go/glm-5.2")
    arena_live.add_argument("--manifest-root", default=Path.cwd(), type=Path)
    arena_live.add_argument("--xa-guard-root", default=None, type=Path)
    arena_live.add_argument("--timeout-seconds", default=180, type=int)

    finding_init = subparsers.add_parser("finding-init", help="write a redteam finding JSON file")
    finding_init.add_argument("--out", required=True, type=Path)
    finding_init.add_argument("--finding-id", required=True)
    finding_init.add_argument("--world", required=True)
    finding_init.add_argument("--target", required=True)
    finding_init.add_argument("--payload-ref", default=None)
    finding_init.add_argument("--task-prompt", required=True)
    finding_init.add_argument("--expected-risk", required=True)
    finding_init.add_argument("--notes", default="")
    finding_init.add_argument("--payload-text", default=None)
    finding_init.add_argument("--payload-path", default=None, type=Path)
    finding_init.add_argument("--manifest-root", default=None, type=Path)

    finding_promote = subparsers.add_parser("finding-promote", help="promote a finding JSON file to challenge JSON")
    finding_promote.add_argument("--finding", required=True, type=Path)
    finding_promote.add_argument("--out", required=True, type=Path)
    finding_promote.add_argument("--expected-decision", default="deny")
    finding_promote.add_argument("--kind", default="attack")
    finding_promote.add_argument("--agent", default="redteam-agent")
    finding_promote.add_argument("--taxonomy", action="append", default=None)

    arena = subparsers.add_parser("arena", help="red-team arena workbench")
    arena_subparsers = arena.add_subparsers(dest="arena_command", required=True)

    arena_worlds = arena_subparsers.add_parser("worlds", help="list available arena worlds")
    arena_worlds.add_argument("--json", action="store_true")

    arena_surfaces = arena_subparsers.add_parser("surfaces", help="show the tool surface for an arena world")
    arena_surfaces.add_argument("--world", default="office-baseline")
    arena_surfaces.add_argument("--json", action="store_true")

    arena_challenges = arena_subparsers.add_parser("challenges", help="list challenges in a suite")
    arena_challenges.add_argument("--suite", default=None, type=Path)
    arena_challenges.add_argument("--manifest-root", default=Path.cwd(), type=Path)
    arena_challenges.add_argument("--json", action="store_true")

    arena_init_finding = arena_subparsers.add_parser("init-finding", help="write a redteam finding JSON file")
    arena_init_finding.add_argument("--out", required=True, type=Path)
    arena_init_finding.add_argument("--finding-id", required=True)
    arena_init_finding.add_argument("--world", required=True)
    arena_init_finding.add_argument("--target", required=True)
    arena_init_finding.add_argument("--payload-ref", default=None)
    arena_init_finding.add_argument("--task-prompt", required=True)
    arena_init_finding.add_argument("--expected-risk", required=True)
    arena_init_finding.add_argument("--notes", default="")
    arena_init_finding.add_argument("--payload-text", default=None)
    arena_init_finding.add_argument("--payload-path", default=None, type=Path)
    arena_init_finding.add_argument("--manifest-root", default=None, type=Path)

    arena_promote = arena_subparsers.add_parser("promote", help="promote a finding JSON file to challenge JSON")
    arena_promote.add_argument("--finding", required=True, type=Path)
    arena_promote.add_argument("--out", required=True, type=Path)
    arena_promote.add_argument("--expected-decision", default="deny")
    arena_promote.add_argument("--kind", default="attack")
    arena_promote.add_argument("--agent", default="redteam-agent")
    arena_promote.add_argument("--taxonomy", action="append", default=None)

    arena_show = arena_subparsers.add_parser("show", help="summarize one live attempt evidence directory")
    arena_show.add_argument("attempt_dir", type=Path)
    arena_show.add_argument("--json", action="store_true")

    arena_run_ab = arena_subparsers.add_parser("run-ab", help="run guard/null live A/B against challenges or one finding")
    arena_run_ab.add_argument("--challenge", action="append", type=Path, default=None)
    arena_run_ab.add_argument("--suite", default=None, type=Path)
    arena_run_ab.add_argument("--finding", default=None, type=Path)
    arena_run_ab.add_argument("--sut-mode", choices=["guard", "null", "both"], default="both")
    arena_run_ab.add_argument("--repeat", default=1, type=int)
    arena_run_ab.add_argument("--out", default=Path("reports"), type=Path)
    arena_run_ab.add_argument("--run-id", default=None)
    arena_run_ab.add_argument("--model", default="opencode-go/glm-5.2")
    arena_run_ab.add_argument("--manifest-root", default=Path.cwd(), type=Path)
    arena_run_ab.add_argument("--xa-guard-root", default=None, type=Path)
    arena_run_ab.add_argument("--timeout-seconds", default=180, type=int)
    arena_run_ab.add_argument("--expected-decision", default="deny")
    arena_run_ab.add_argument("--kind", default="attack")
    arena_run_ab.add_argument("--agent", default="redteam-agent")
    arena_run_ab.add_argument("--taxonomy", action="append", default=None)
    return parser

def run_finding_cli(args: argparse.Namespace) -> int:
    from .arena.findings import create_finding, promote_finding_to_challenge

    if args.command == "finding-init":
        finding = create_finding(
            path=args.out,
            finding_id=args.finding_id,
            world=args.world,
            target=args.target,
            payload_ref=args.payload_ref,
            task_prompt=args.task_prompt,
            expected_risk=args.expected_risk,
            notes=args.notes,
            payload_text=args.payload_text,
            payload_path=args.payload_path,
            manifest_root=args.manifest_root,
        )
        print(json.dumps({"finding": str(args.out), **finding.__dict__}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "finding-promote":
        challenge = promote_finding_to_challenge(
            args.finding,
            output_path=args.out,
            expected_decision=args.expected_decision,
            kind=args.kind,
            agent=args.agent,
            taxonomy=args.taxonomy,
        )
        print(json.dumps({"challenge": str(args.out), **challenge}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    raise ValueError(f"unsupported finding command {args.command!r}")



def _run_live_from_args(args: argparse.Namespace, challenge_paths: list[Path] | None = None) -> int:
    from .arena.live import default_challenge_paths, run_live_suite
    from .arena.suite import load_suite

    sut_modes = ["guard", "null"] if args.sut_mode == "both" else [args.sut_mode]
    if challenge_paths is None:
        if args.challenge:
            challenge_paths = args.challenge
        elif getattr(args, "suite", None) is not None:
            challenge_paths = load_suite(args.suite).resolved_paths(args.manifest_root)
        else:
            challenge_paths = default_challenge_paths(args.manifest_root)
    manifest = run_live_suite(
        challenge_paths=challenge_paths,
        manifest_root=args.manifest_root,
        output_root=args.out,
        run_id=args.run_id,
        sut_modes=sut_modes,
        repeats=args.repeat,
        model=args.model,
        xa_guard_root=args.xa_guard_root,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def run_arena_cli(args: argparse.Namespace) -> int:
    if args.arena_command == "worlds":
        from .arena.worlds import list_worlds

        rows = [
            {
                "world_id": world.world_id,
                "title": world.title,
                "description": world.description,
                "default_principal": world.default_principal,
                "injection_targets": list(world.injection_targets),
            }
            for world in list_worlds()
        ]
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for row in rows:
                print(f"{row['world_id']}\t{row['default_principal']}\t{row['title']}")
        return 0

    if args.arena_command == "surfaces":
        from .arena.surface import office_tool_surface

        if args.world != "office-baseline":
            raise ValueError(f"unknown surface world: {args.world}")
        surface = office_tool_surface()
        rows = [
            {
                "name": tool.name,
                "description": tool.description,
                "capabilities": tool.capabilities,
                "input_max_taint": tool.input_max_taint,
                "output_taint": tool.output_taint,
                "risk_level": tool.risk_level,
                "metadata": tool.metadata,
            }
            for tool in surface.tools
        ]
        if args.json:
            print(json.dumps({"surface": surface.name, "tools": rows}, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for row in rows:
                print(f"{row['name']}\t{row['risk_level']}\t{','.join(row['capabilities'])}")
        return 0

    if args.arena_command == "challenges":
        from .arena.challenge import load_challenge
        from .arena.suite import suite_from_arg, suite_to_json

        suite = suite_from_arg(args.suite)
        rows = []
        for path in suite.resolved_paths(args.manifest_root):
            challenge = load_challenge(path)
            rows.append(
                {
                    "challenge_id": challenge.challenge_id,
                    "kind": challenge.kind,
                    "world": challenge.world,
                    "taxonomy": challenge.taxonomy,
                    "path": str(path),
                    "principal": challenge.task.principal,
                    "expected_decision": challenge.oracle.expected_decision,
                }
            )
        if args.json:
            print(json.dumps({"suite": suite_to_json(suite), "challenges": rows}, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for row in rows:
                print(f"{row['challenge_id']}\t{row['kind']}\t{row['world']}\t{row['expected_decision']}")
        return 0

    if args.arena_command == "init-finding":
        from .arena.findings import create_finding

        finding = create_finding(
            path=args.out,
            finding_id=args.finding_id,
            world=args.world,
            target=args.target,
            payload_ref=args.payload_ref,
            task_prompt=args.task_prompt,
            expected_risk=args.expected_risk,
            notes=args.notes,
            payload_text=args.payload_text,
            payload_path=args.payload_path,
            manifest_root=args.manifest_root,
        )
        print(json.dumps({"finding": str(args.out), **finding.__dict__}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.arena_command == "promote":
        from .arena.findings import promote_finding_to_challenge

        challenge = promote_finding_to_challenge(
            args.finding,
            output_path=args.out,
            expected_decision=args.expected_decision,
            kind=args.kind,
            agent=args.agent,
            taxonomy=args.taxonomy,
        )
        print(json.dumps({"challenge": str(args.out), **challenge}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.arena_command == "show":
        from .arena.evidence import AttemptPaths
        from .io_utils import read_json

        paths = AttemptPaths.for_attempt(args.attempt_dir)
        verdict = read_json(paths.verdict) if paths.verdict.exists() else {}
        artifact_hashes = read_json(paths.artifact_hashes) if paths.artifact_hashes.exists() else {}
        verdict_body = verdict.get("verdict", {}) if isinstance(verdict.get("verdict", {}), dict) else {}
        summary = {
            "attempt_dir": str(args.attempt_dir),
            "challenge_id": verdict.get("challenge_id"),
            "kind": verdict.get("kind"),
            "sut_mode": verdict.get("sut_mode"),
            "passed": verdict_body.get("passed"),
            "observed_decision": verdict_body.get("observed_decision"),
            "data_exposure": verdict_body.get("data_exposure"),
            "external_send_count": verdict_body.get("external_send_count"),
            "returncode": verdict.get("returncode"),
            "opencode_event_count": verdict.get("opencode_event_count", 0),
            "audit_record_count": verdict.get("audit_record_count", 0),
            "egress_record_count": verdict.get("egress_record_count", 0),
            "artifact_count": len(artifact_hashes),
        }
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for key, value in summary.items():
                print(f"{key}: {value}")
        return 0

    if args.arena_command == "run-ab":
        challenge_paths = args.challenge
        if args.finding is not None:
            from .arena.findings import load_finding, promote_finding_to_challenge

            finding = load_finding(args.finding)
            promoted_path = args.out / "_arena_promoted" / f"{finding.finding_id}.{args.kind}.json"
            promote_finding_to_challenge(
                finding,
                output_path=promoted_path,
                expected_decision=args.expected_decision,
                kind=args.kind,
                agent=args.agent,
                taxonomy=args.taxonomy,
            )
            challenge_paths = [promoted_path]
        return _run_live_from_args(args, challenge_paths=challenge_paths)

    raise ValueError(f"unsupported arena command {args.arena_command!r}")

def main(argv: list[str] | None = None) -> int:
    # Emit UTF-8 so non-ASCII output (e.g. Chinese capability titles) survives a
    # legacy Windows console codepage. No-op for ASCII output and for streams
    # (like StringIO) that do not support reconfigure.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        manifest = load_manifest(args.manifest)
        print(f"manifest: {manifest.path}")
        print(f"cases: {len(manifest.cases)}")
        print(f"fixtures: {len(manifest.fixtures)}")
        for warning in manifest.validation.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        for error in manifest.validation.errors:
            print(f"error: {error}", file=sys.stderr)
        return 0 if manifest.validation.ok else 1

    if args.command == "run":
        summary = run_cases(
            manifest_path=args.manifest,
            output_root=args.out,
            adapter_id=args.adapter,
            sut_id=args.sut_id,
            mode=args.mode,
            operator=args.operator,
            seed=args.seed,
            run_id=args.run_id,
        )
        print(f"run_id: {summary.run_id}")
        print(f"run_dir: {summary.run_dir}")
        print("metrics:")
        print(json.dumps(summary.metrics, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "compare":
        paths = compare_run_outputs(
            baseline_dir=args.baseline,
            candidate_dir=args.candidate,
            output_dir=args.out,
        )
        print("compare outputs:")
        print(json.dumps(paths, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "tools":
        print(json.dumps(TOOL_DEFINITIONS, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "p2-status":
        from .p2.registry import as_dicts

        rows = as_dicts()
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for row in rows:
                print(f"{row['key']:12} [{row['status']}] {row['title']}")
        return 0

    if args.command == "serve-stdio":
        state = build_protocol_state(manifest_root=args.manifest_root, run_id=args.run_id, sut_id=args.sut_id)
        return serve_stdio(state)

    if args.command == "serve-http":
        state = build_protocol_state(manifest_root=args.manifest_root, run_id=args.run_id, sut_id=args.sut_id)
        serve_http(state, host=args.host, port=args.port)
        return 0

    if args.command == "ide-replay":
        state = build_protocol_state(manifest_root=args.manifest_root, run_id=args.run_id, sut_id=args.sut_id)
        for response in replay_ide_file(state, args.replay_file):
            print(json.dumps(response, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "arena-live":
        return _run_live_from_args(args)

    if args.command in {"finding-init", "finding-promote"}:
        return run_finding_cli(args)

    if args.command == "arena":
        return run_arena_cli(args)

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
