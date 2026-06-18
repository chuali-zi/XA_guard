from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from bench.external import ADAPTER_VERSION, SCHEMA_VERSION
from bench.external.provenance import file_sha256
from bench.external.schema import validate_record


def build_report(
    records: Iterable[dict[str, Any]],
    *,
    input_path: str | Path,
) -> dict[str, Any]:
    """Build an auditable non-official report for normalized external results."""
    path = Path(input_path)
    rows = list(records)
    validation_errors: list[dict[str, Any]] = []
    benchmark_counts: Counter[str] = Counter()
    suite_counts: Counter[str] = Counter()
    limitation_counts: Counter[str] = Counter()
    records_with_attack_label = 0
    records_with_benign_label = 0
    attack_success = 0
    benign_success = 0

    for index, record in enumerate(rows):
        for error in validate_record(record):
            validation_errors.append({"record_index": index, "error": error})

        benchmark = record.get("benchmark", {}) or {}
        case = record.get("case", {}) or {}
        observed = record.get("observed", {}) or {}
        benchmark_counts[str(benchmark.get("name") or "unknown")] += 1
        suite_counts[str(benchmark.get("suite") or case.get("task_type") or "unknown")] += 1
        for limitation in record.get("limitations") or []:
            limitation_counts[str(limitation)] += 1

        if observed.get("attack_success") is not None:
            records_with_attack_label += 1
            if observed.get("attack_success") is True:
                attack_success += 1
        if observed.get("benign_success") is not None:
            records_with_benign_label += 1
            if observed.get("benign_success") is True:
                benign_success += 1

    return {
        "schema_version": "xa-external-bench-report/v0.1",
        "adapter_schema_version": SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "input": {
            "path": str(path),
            "sha256": file_sha256(path),
        },
        "records": {
            "total": len(rows),
            "valid": len(rows) - len({err["record_index"] for err in validation_errors}),
            "invalid": len({err["record_index"] for err in validation_errors}),
            "validation_errors": validation_errors,
        },
        "coverage": {
            "benchmarks": dict(sorted(benchmark_counts.items())),
            "suites_or_task_types": dict(sorted(suite_counts.items())),
            "records_with_attack_label": records_with_attack_label,
            "records_with_benign_label": records_with_benign_label,
        },
        "smoke_metrics": {
            "attack_success_count_if_labeled": attack_success,
            "attack_success_rate_if_labeled": (
                attack_success / records_with_attack_label if records_with_attack_label else None
            ),
            "benign_success_count_if_labeled": benign_success,
            "benign_success_rate_if_labeled": (
                benign_success / records_with_benign_label if records_with_benign_label else None
            ),
        },
        "limitations": {
            "official_claim": False,
            "not_official_benchmark_score": True,
            "adapter_only": True,
            "counts": dict(sorted(limitation_counts.items())),
            "notes": [
                "normalized_user_provided_exports_only",
                "does_not_run_official_agentdojo_or_injecagent",
                "do_not_compare_as_official_asr_or_utility",
            ],
        },
        "recommended_archive": {
            "normalized_jsonl": str(path),
            "report_json": "external-report.json",
            "source_export_sha256": "see each record.adapter.input_sha256",
            "include_in_submission": False,
            "submission_use": "supporting evidence only; not official benchmark score",
        },
    }
