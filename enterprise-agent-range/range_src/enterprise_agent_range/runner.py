from __future__ import annotations

import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .adapters import get_adapter
from .fixtures import load_manifest
from .io_utils import sha256_file, sha256_text, stable_json_dumps, utc_now_iso
from .models import CaseResult
from .oracles import aggregate_metrics, evaluate_case, status_from_outcomes
from .reports import write_run_outputs
from .systems import RangeState


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    run_dir: Path
    metrics: dict[str, Any]
    output_paths: dict[str, str]


def run_cases(
    *,
    manifest_path: Path,
    output_root: Path,
    adapter_id: str = "null_adapter",
    sut_id: str = "null-baseline",
    mode: str = "local",
    operator: str = "local",
    seed: int = 20260701,
    run_id: str | None = None,
) -> RunSummary:
    manifest = load_manifest(manifest_path)
    if not manifest.validation.ok:
        raise ValueError("manifest validation failed: " + "; ".join(manifest.validation.errors))

    run_id = run_id or "run-" + utc_now_iso().replace(":", "").replace("+0000", "Z").replace("+00:00", "Z")
    project_root = manifest.root
    environment = build_environment(project_root, seed)
    environment_hash = sha256_text(stable_json_dumps(environment))
    state = RangeState(
        run_id=run_id,
        sut_id=sut_id,
        environment_hash=environment_hash,
        manifest_root=project_root,
    )
    adapter = get_adapter(adapter_id)
    case_rows: list[dict[str, Any]] = []
    for case in manifest.cases:
        if case.get("case_kind") == "exploratory_finding" or case.get("surface") == "manual":
            continue
        execution = adapter.run_case(case, state)
        outcomes = evaluate_case(execution)
        status = status_from_outcomes(execution, outcomes)
        result = CaseResult(
            run_id=run_id,
            case_id=str(case["case_id"]),
            trace_id=execution.trace_id,
            case_kind=str(case["case_kind"]),
            taxonomy=list(case.get("taxonomy", [])),
            domain=str(case.get("domain", "")),
            surface=str(case.get("surface", "")),
            expected=dict(case.get("expected", {})),
            actual=execution.actual,
            status=status,
            latency_ms=execution.latency_ms,
            oracle_results=outcomes,
            evidence_refs={
                "case_result": "case-results.jsonl",
                "side_effect_log": "side-effects.jsonl",
                "audit_record": "audit-records.jsonl",
            },
            infra_error=execution.infra_error,
        ).to_json()
        result["title"] = case.get("title", "")
        case_rows.append(result)

    metrics = aggregate_metrics(case_rows, state.audit_records)
    run_manifest = {
        "run_id": run_id,
        "started_at": utc_now_iso(),
        "range_version": __version__,
        "case_manifest_hash": sha256_file(manifest.path),
        "sut_id": sut_id,
        "sut_adapter": adapter.adapter_id,
        "operator": operator,
        "mode": mode,
        "manifest_warnings": manifest.validation.warnings,
    }
    run_dir = output_root / run_id
    output_paths = write_run_outputs(
        run_dir=run_dir,
        project_root=project_root,
        manifest=manifest,
        run_manifest=run_manifest,
        environment=environment,
        case_results=case_rows,
        side_effects=state.side_effects,
        audit_records=state.audit_records,
        metrics=metrics,
    )
    return RunSummary(run_id=run_id, run_dir=run_dir, metrics=metrics, output_paths=output_paths)


def build_environment(project_root: Path, seed: int) -> dict[str, Any]:
    return {
        "os": platform.platform(),
        "python_version": sys.version.split()[0],
        "container_runtime": "none",
        "network_mode": "offline",
        "timezone": os.environ.get("TZ") or "local",
        "seed": seed,
        "dirty_state": git_dirty_state(project_root),
    }


def git_dirty_state(project_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--", str(project_root)],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return "dirty" if result.stdout.strip() else "clean"
