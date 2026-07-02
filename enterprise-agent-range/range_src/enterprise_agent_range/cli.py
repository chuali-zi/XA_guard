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
    return parser


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

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
