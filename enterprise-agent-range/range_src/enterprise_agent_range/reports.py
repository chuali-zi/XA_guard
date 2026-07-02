from __future__ import annotations

from pathlib import Path
from typing import Any

from .fixtures import fixture_hashes
from .io_utils import relative_to_root, sha256_file, write_json, write_jsonl
from .models import LoadedManifest


def write_run_outputs(
    *,
    run_dir: Path,
    project_root: Path,
    manifest: LoadedManifest,
    run_manifest: dict[str, Any],
    environment: dict[str, Any],
    case_results: list[dict[str, Any]],
    side_effects: list[dict[str, Any]],
    audit_records: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> dict[str, str]:
    run_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "run_manifest": run_dir / "run-manifest.json",
        "environment": run_dir / "environment.json",
        "case_results": run_dir / "case-results.jsonl",
        "side_effects": run_dir / "side-effects.jsonl",
        "audit_records": run_dir / "audit-records.jsonl",
        "metrics": run_dir / "metrics.json",
        "report": run_dir / "report.md",
        "artifact_hashes": run_dir / "artifact-hashes.json",
    }

    write_json(paths["run_manifest"], run_manifest)
    write_json(paths["environment"], environment)
    write_jsonl(paths["case_results"], case_results)
    write_jsonl(paths["side_effects"], side_effects)
    write_jsonl(paths["audit_records"], audit_records)
    write_json(paths["metrics"], metrics)
    paths["report"].write_text(render_markdown_report(run_manifest, metrics, case_results), encoding="utf-8", newline="\n")

    artifact_hashes = build_artifact_hashes(paths, manifest, project_root)
    write_json(paths["artifact_hashes"], artifact_hashes)
    return {name: relative_to_root(path, project_root) for name, path in paths.items()}


def build_artifact_hashes(
    paths: dict[str, Path],
    manifest: LoadedManifest,
    project_root: Path,
) -> dict[str, str]:
    hashes: dict[str, str] = {
        relative_to_root(manifest.path, project_root): sha256_file(manifest.path),
    }
    for fixture_path, digest in fixture_hashes(manifest).items():
        hashes[fixture_path] = digest
    for name, path in paths.items():
        if name == "artifact_hashes":
            continue
        hashes[relative_to_root(path, project_root)] = sha256_file(path)
    return hashes


def render_markdown_report(
    run_manifest: dict[str, Any],
    metrics: dict[str, Any],
    case_results: list[dict[str, Any]],
) -> str:
    counts = metrics.get("counts", {})
    failed = [row for row in case_results if row.get("status") == "FAIL"]
    lines = [
        f"# Enterprise Agent Range Report: {run_manifest['run_id']}",
        "",
        "## Run",
        "",
        f"- Adapter: `{run_manifest['sut_adapter']}`",
        f"- SUT: `{run_manifest['sut_id']}`",
        f"- Mode: `{run_manifest['mode']}`",
        f"- Started: `{run_manifest['started_at']}`",
        "",
        "## Metrics",
        "",
        f"- Total cases: {counts.get('total_cases', 0)}",
        f"- Valid cases: {counts.get('valid_cases', 0)}",
        f"- PASS / FAIL / INFRA_ERROR / INVALID: {counts.get('pass', 0)} / {counts.get('fail', 0)} / {counts.get('infra_error', 0)} / {counts.get('invalid', 0)}",
        f"- ASR: {metrics.get('attack_success_rate')}",
        f"- FPR: {metrics.get('false_positive_rate')}",
        f"- Utility: {metrics.get('utility_retention')}",
        f"- Zero Effect: {metrics.get('downstream_zero_effect_rate')}",
        f"- Data Exposure: {metrics.get('data_exposure_rate')}",
        f"- Audit Completeness: {metrics.get('audit_completeness')}",
        f"- Audit Integrity: {metrics.get('audit_integrity')}",
        f"- Run Audit Chain Valid: {metrics.get('run_audit_chain_valid')}",
        f"- Assurance Pass Rate: {metrics.get('assurance_pass_rate')}",
        "",
        "## Failed Cases",
        "",
    ]
    if not failed:
        lines.append("- None")
    else:
        for row in failed[:50]:
            failed_oracles = [
                outcome["name"]
                for outcome in row.get("oracle_results", [])
                if not outcome.get("passed")
            ]
            lines.append(f"- `{row['case_id']}` {row['title'] if 'title' in row else ''} ({', '.join(failed_oracles)})")
        if len(failed) > 50:
            lines.append(f"- ... {len(failed) - 50} more")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Null Adapter is an intentionally unprotected baseline. Attack-case failures indicate exploitable behavior in the baseline, not a range runtime failure.")
    lines.append("- All side effects are local synthetic sinks; no production API, external email, or real shell command is invoked.")
    lines.append("")
    return "\n".join(lines)
