from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from bench.external import ADAPTER_VERSION, SCHEMA_VERSION
from bench.external.normalizers.agentdojo import normalize_agentdojo
from bench.external.normalizers.base import read_records, write_jsonl
from bench.external.normalizers.injecagent import normalize_injecagent
from bench.external.provenance import file_sha256
from bench.external.projection import run_projection
from bench.external.report import build_report
from bench.external.schema import validate_record
from xa_guard.audit.archive import verify_audit_jsonl

_NORMALIZERS = {
    "agentdojo": normalize_agentdojo,
    "injecagent": normalize_injecagent,
}


def _cmd_normalize(args: argparse.Namespace) -> int:
    source = Path(args.input)
    records = read_records(source)
    input_hash = file_sha256(source)
    normalizer = _NORMALIZERS[args.benchmark]
    normalized = [
        normalizer(record, input_sha256=input_hash, index=index)
        for index, record in enumerate(records)
    ]
    count = write_jsonl(normalized, args.output)
    output = Path(args.output)
    print(
        json.dumps(
            {
                "command": "normalize",
                "benchmark": args.benchmark,
                "official_claim": False,
                "claim_scope": "adapter_only_not_official_reproduction",
                "schema_version": SCHEMA_VERSION,
                "adapter_version": ADAPTER_VERSION,
                "input": str(source),
                "input_sha256": input_hash,
                "input_bytes": source.stat().st_size,
                "records_read": len(records),
                "records_written": count,
                "output": str(output),
                "output_sha256": file_sha256(output),
                "limitations": [
                    "adapter_only",
                    "not_official_reproduction",
                    "input_user_provided",
                    "no_large_dependency_download",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _iter_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line:
                continue
            yield line_no, json.loads(line)


def _cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.input)
    summary = _validation_summary(path)
    payload = {
        "command": "validate",
        "official_claim": False,
        "input": str(path),
        "input_sha256": file_sha256(path),
        "schema_version": SCHEMA_VERSION,
        "records_total": summary["records_total"],
        "records_valid": summary["records_total"] - len({err["line"] for err in summary["errors"]}),
        "errors_count": len(summary["errors"]),
        "errors": summary["errors"],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not summary["errors"] else 1


def _validation_summary(path: Path) -> dict:
    errors = []
    count = 0
    for line_no, record in _iter_jsonl(path):
        count += 1
        for error in validate_record(record):
            errors.append({"line": line_no, "error": error})
    return {"records_total": count, "errors": errors}


def _smoke_metrics(path: Path) -> dict:
    total = 0
    valid = 0
    attack_labeled = 0
    attack_success = 0
    benign_labeled = 0
    for _, record in _iter_jsonl(path):
        total += 1
        if not validate_record(record):
            valid += 1
        observed = record.get("observed", {})
        if observed.get("attack_success") is not None:
            attack_labeled += 1
            attack_success += 1 if observed.get("attack_success") is True else 0
        if observed.get("benign_success") is not None:
            benign_labeled += 1

    rate = attack_success / attack_labeled if attack_labeled else None
    return {
        "command": "smoke-metrics",
        "metric_scope": "adapter_health_only",
        "not_official_benchmark_score": True,
        "records_total": total,
        "records_valid": valid,
        "records_with_attack_label": attack_labeled,
        "records_with_benign_label": benign_labeled,
        "attack_success_rate_if_labeled": rate,
        "official_claim": False,
        "input": str(path),
        "input_sha256": file_sha256(path),
        "disclaimer": (
            "This is computed from user-provided labels after normalization. "
            "It is not AgentDojo ASR, InjecAgent ASR, or an official reproduction."
        ),
        "notes": ["adapter_smoke_metric_only", "not_official_benchmark_score"],
    }


def _cmd_smoke_metrics(args: argparse.Namespace) -> int:
    print(json.dumps(_smoke_metrics(Path(args.input)), ensure_ascii=False, indent=2))
    return 0


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _audit_edge_hashes(path: Path) -> dict:
    first = ""
    last = ""
    if not path.exists():
        return {"first_record_hash": "", "last_record_hash": ""}
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            record = json.loads(line)
            record_hash = str(record.get("record_hash") or "")
            if not first:
                first = record_hash
            last = record_hash
    return {"first_record_hash": first, "last_record_hash": last}


def _cmd_report(args: argparse.Namespace) -> int:
    path = Path(args.input)
    records = [record for _, record in _iter_jsonl(path)]
    report = build_report(records, input_path=path)
    if args.output:
        _write_json(Path(args.output), report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _cmd_archive(args: argparse.Namespace) -> int:
    source = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = read_records(source)
    input_hash = file_sha256(source)
    normalizer = _NORMALIZERS[args.benchmark]
    normalized = [
        normalizer(record, input_sha256=input_hash, index=index)
        for index, record in enumerate(records)
    ]

    normalized_path = out_dir / "normalized.jsonl"
    write_jsonl(normalized, normalized_path)
    validation_path = out_dir / "validation.json"
    metrics_path = out_dir / "smoke-metrics.json"
    report_path = out_dir / "report.json"
    projection_dir = out_dir / "xa-guard-projection"
    projection_path = projection_dir / "results.json"
    projection_summary_path = projection_dir / "summary.json"
    projection_audit_verify_path = projection_dir / "audit-verify.json"
    manifest_path = out_dir / "manifest.json"
    readme_path = out_dir / "README.md"

    validation = _validation_summary(normalized_path)
    metrics = _smoke_metrics(normalized_path)
    report = build_report(normalized, input_path=normalized_path)
    projection_results = None
    projection_summary = None
    projection_audit_verify = None
    if args.run_projection:
        projection_audit_dir = projection_dir / "audit"
        projection_results = run_projection(
            normalized,
            audit_dir=projection_audit_dir,
            config_path=args.config,
        )
        _write_json(projection_path, {"results": projection_results})
        projection_audit_path = projection_audit_dir / "audit.jsonl"
        projection_audit_verify = {
            **verify_audit_jsonl(projection_audit_path, algo="sha256"),
            "algo": "sha256",
            "audit_path": str(projection_audit_path),
            "audit_sha256": file_sha256(projection_audit_path) if projection_audit_path.exists() else "",
            **_audit_edge_hashes(projection_audit_path),
        }
        _write_json(projection_audit_verify_path, projection_audit_verify)
        expected = [
            item
            for item in projection_results
            if item.get("matches_expected_decision") is not None
        ]
        projection_summary = {
            "claim_scope": "xa_guard_local_projection_only",
            "official_claim": False,
            "not_official_benchmark_score": True,
            "does_not_run_official_environment": True,
            "not_comparable_to_agentdojo_or_injecagent_leaderboard": True,
            "records_projected": len(projection_results),
            "records_with_expected_decision": len(expected),
            "xa_guard_projection_expected_decision_match_rate": (
                sum(1 for item in expected if item.get("matches_expected_decision") is True) / len(expected)
                if expected
                else None
            ),
            "xa_guard_projection_deny_rate": (
                sum(1 for item in projection_results if item.get("xa_guard_decision") == "deny")
                / len(projection_results)
                if projection_results
                else None
            ),
            "records_not_projectable": 0,
            "projection_infra_errors": 0,
        }
        _write_json(projection_summary_path, projection_summary)

    schema_path = Path("bench/schema/external-benchmark-result.schema.json")
    limitation_counts = report.get("limitations", {}).get("counts", {})
    limitations = sorted(set(limitation_counts) | {"not_official_reproduction", "adapter_only"})

    manifest = {
        "schema_version": "xa-external-benchmark-archive/v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "benchmark": args.benchmark,
        "adapter_version": ADAPTER_VERSION,
        "adapter_schema_version": SCHEMA_VERSION,
        "official_claim": False,
        "limitations": limitations,
        "input": {
            "path": str(source),
            "sha256": input_hash,
            "bytes": source.stat().st_size,
        },
        "normalized": {
            "path": str(normalized_path),
            "sha256": file_sha256(normalized_path),
            "records_total": len(normalized),
        },
        "schema": {
            "path": str(schema_path),
            "sha256": file_sha256(schema_path) if schema_path.exists() else "",
        },
        "outputs": {
            "validation": str(validation_path),
            "smoke_metrics": str(metrics_path),
            "report": str(report_path),
            "projection_results": str(projection_path) if projection_results is not None else "",
            "projection_summary": str(projection_summary_path) if projection_results is not None else "",
            "projection_audit_verify": (
                str(projection_audit_verify_path) if projection_results is not None else ""
            ),
            "readme": str(readme_path),
        },
        "commands": {
            "archive": {
                "benchmark": args.benchmark,
                "input": str(source),
                "out_dir": str(out_dir),
                "run_projection": bool(args.run_projection),
                "config": str(args.config) if args.config else "",
            }
        },
        "validation": {
            "errors": len(validation["errors"]),
            "records_total": validation["records_total"],
        },
        "notes": [
            "adapter_only_archive",
            "not_official_benchmark_score",
            "does_not_run_official_agentdojo_or_injecagent",
        ],
    }
    if projection_results is not None:
        projection_matches = [
            item.get("matches_expected_decision")
            for item in projection_results
            if item.get("matches_expected_decision") is not None
        ]
        manifest["projection"] = {
            "enabled": True,
            "claim_scope": "xa_guard_local_projection_only",
            "official_claim": False,
            "not_official_benchmark_score": True,
            "does_not_run_official_environment": True,
            "not_comparable_to_agentdojo_or_injecagent_leaderboard": True,
            "path": str(projection_path),
            "sha256": file_sha256(projection_path),
            "summary_path": str(projection_summary_path),
            "summary_sha256": file_sha256(projection_summary_path),
            "records_total": len(projection_results),
            "records_with_expected_decision": len(projection_matches),
            "matches_expected_decision": sum(1 for item in projection_matches if item is True),
            "audit_dir": str(projection_dir / "audit"),
            "audit_path": str(projection_dir / "audit" / "audit.jsonl"),
            "audit_sha256": (
                projection_audit_verify.get("audit_sha256", "") if projection_audit_verify else ""
            ),
            "audit_verify": projection_audit_verify or {},
            "config": {
                "path": str(args.config) if args.config else "",
                "sha256": file_sha256(args.config) if args.config else "",
            },
            "metric_scope": "xa_guard_projection_only_not_official_benchmark_score",
        }
    else:
        manifest["projection"] = {"enabled": False}

    _write_json(validation_path, validation)
    _write_json(metrics_path, metrics)
    _write_json(report_path, report)
    _write_json(manifest_path, manifest)
    readme_path.write_text(
        "\n".join(
            [
                "# XA-Guard External Benchmark Archive",
                "",
                f"- Benchmark adapter: `{args.benchmark}`",
                "- Official claim: `false`",
                "- Scope: adapter-only normalization of user-provided exports.",
                "- This archive is supporting evidence only; do not compare it as official ASR/utility.",
                "",
                "Files:",
                "- `normalized.jsonl`: normalized records.",
                "- `validation.json`: schema validation summary.",
                "- `smoke-metrics.json`: adapter smoke metrics, not official benchmark metrics.",
                "- `report.json`: auditable summary report.",
                "- `xa-guard-projection/results.json`: optional local XA-Guard projection decisions when `--run-projection` is used.",
                "- `xa-guard-projection/summary.json`: optional projection summary; not an official benchmark score.",
                "- `xa-guard-projection/audit/audit.jsonl`: isolated projection audit log when projection is enabled.",
                "- `xa-guard-projection/audit-verify.json`: optional projection audit chain verification.",
                "- `manifest.json`: hashes, versions, limitations, and archive provenance.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(json.dumps({"archive_dir": str(out_dir), "manifest": str(manifest_path), "official_claim": False}, indent=2))
    return 0 if not validation["errors"] else 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m bench.external.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    normalize = sub.add_parser("normalize")
    normalize.add_argument("--benchmark", required=True, choices=sorted(_NORMALIZERS))
    normalize.add_argument("--input", required=True)
    normalize.add_argument("--output", required=True)
    normalize.set_defaults(func=_cmd_normalize)

    validate = sub.add_parser("validate")
    validate.add_argument("--input", required=True)
    validate.set_defaults(func=_cmd_validate)

    metrics = sub.add_parser("smoke-metrics")
    metrics.add_argument("--input", required=True)
    metrics.set_defaults(func=_cmd_smoke_metrics)

    report = sub.add_parser("report")
    report.add_argument("--input", required=True)
    report.add_argument("--output")
    report.set_defaults(func=_cmd_report)

    archive = sub.add_parser("archive")
    archive.add_argument("--benchmark", required=True, choices=sorted(_NORMALIZERS))
    archive.add_argument("--input", required=True)
    archive.add_argument("--out-dir", required=True)
    archive.add_argument(
        "--run-projection",
        action="store_true",
        help="Run normalized xa_guard_projection payloads through XA-Guard as supporting evidence.",
    )
    archive.add_argument(
        "--config",
        help="Optional XA-Guard config for --run-projection; default uses in-memory defaults.",
    )
    archive.set_defaults(func=_cmd_archive)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
