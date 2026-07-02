from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from .fixtures import fixture_hashes
from .io_utils import read_json, relative_to_root, sha256_file, write_json, write_jsonl
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
        "report_html": run_dir / "report.html",
        "artifact_hashes": run_dir / "artifact-hashes.json",
    }

    write_json(paths["run_manifest"], run_manifest)
    write_json(paths["environment"], environment)
    write_jsonl(paths["case_results"], case_results)
    write_jsonl(paths["side_effects"], side_effects)
    write_jsonl(paths["audit_records"], audit_records)
    write_json(paths["metrics"], metrics)
    paths["report"].write_text(render_markdown_report(run_manifest, metrics, case_results), encoding="utf-8", newline="\n")
    paths["report_html"].write_text(render_html_report(run_manifest, metrics, case_results), encoding="utf-8", newline="\n")

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


def render_html_report(
    run_manifest: dict[str, Any],
    metrics: dict[str, Any],
    case_results: list[dict[str, Any]],
) -> str:
    counts = metrics.get("counts", {})
    failed = [row for row in case_results if row.get("status") == "FAIL"]
    metric_rows = [
        ("Total cases", counts.get("total_cases", 0)),
        ("Valid cases", counts.get("valid_cases", 0)),
        ("PASS", counts.get("pass", 0)),
        ("FAIL", counts.get("fail", 0)),
        ("INFRA_ERROR", counts.get("infra_error", 0)),
        ("INVALID", counts.get("invalid", 0)),
        ("ASR", metrics.get("attack_success_rate")),
        ("FPR", metrics.get("false_positive_rate")),
        ("Utility", metrics.get("utility_retention")),
        ("Zero Effect", metrics.get("downstream_zero_effect_rate")),
        ("Data Exposure", metrics.get("data_exposure_rate")),
        ("Audit Completeness", metrics.get("audit_completeness")),
        ("Audit Integrity", metrics.get("audit_integrity")),
        ("Run Audit Chain Valid", metrics.get("run_audit_chain_valid")),
        ("Assurance Pass Rate", metrics.get("assurance_pass_rate")),
    ]
    failed_rows = []
    for row in failed[:50]:
        failed_oracles = [
            outcome.get("name")
            for outcome in row.get("oracle_results", [])
            if not outcome.get("passed")
        ]
        failed_rows.append(
            "<tr>"
            f"<td>{_html(row.get('case_id', ''))}</td>"
            f"<td>{_html(row.get('title', ''))}</td>"
            f"<td>{_html(', '.join(str(item) for item in failed_oracles))}</td>"
            "</tr>"
        )
    if not failed_rows:
        failed_body = '<tr><td colspan="3">None</td></tr>'
    else:
        failed_body = "\n".join(failed_rows)
        if len(failed) > 50:
            failed_body += f'\n<tr><td colspan="3">{_html(f"... {len(failed) - 50} more")}</td></tr>'

    metrics_body = "\n".join(
        f"<tr><th scope=\"row\">{_html(name)}</th><td>{_html(value)}</td></tr>"
        for name, value in metric_rows
    )
    run_id = run_manifest.get("run_id", "")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Enterprise Agent Range Report: {_html(run_id)}</title>
  <style>
    body {{ color: #1f2933; font-family: Arial, sans-serif; line-height: 1.5; margin: 2rem; }}
    h1, h2 {{ color: #102a43; }}
    table {{ border-collapse: collapse; margin: 1rem 0 2rem; width: 100%; }}
    th, td {{ border: 1px solid #bcccdc; padding: 0.5rem 0.65rem; text-align: left; vertical-align: top; }}
    th {{ background: #f0f4f8; }}
    code {{ background: #f0f4f8; padding: 0.1rem 0.25rem; }}
  </style>
</head>
<body>
  <h1>Enterprise Agent Range Report: {_html(run_id)}</h1>
  <h2>Run</h2>
  <table>
    <tbody>
      <tr><th scope="row">Adapter</th><td><code>{_html(run_manifest.get("sut_adapter", ""))}</code></td></tr>
      <tr><th scope="row">SUT</th><td><code>{_html(run_manifest.get("sut_id", ""))}</code></td></tr>
      <tr><th scope="row">Mode</th><td><code>{_html(run_manifest.get("mode", ""))}</code></td></tr>
      <tr><th scope="row">Started</th><td>{_html(run_manifest.get("started_at", ""))}</td></tr>
    </tbody>
  </table>
  <h2>Metrics</h2>
  <table><tbody>
{metrics_body}
  </tbody></table>
  <h2>Failed Cases</h2>
  <table>
    <thead><tr><th scope="col">Case ID</th><th scope="col">Title</th><th scope="col">Failed Oracles</th></tr></thead>
    <tbody>
{failed_body}
    </tbody>
  </table>
  <h2>Notes</h2>
  <ul>
    <li>Null Adapter is an intentionally unprotected baseline. Attack-case failures indicate exploitable behavior in the baseline, not a range runtime failure.</li>
    <li>All side effects are local synthetic sinks; no production API, external email, or real shell command is invoked.</li>
  </ul>
</body>
</html>
"""


def compare_run_outputs(
    *,
    baseline_dir: Path,
    candidate_dir: Path,
    output_dir: Path,
) -> dict[str, str]:
    comparison = build_run_comparison(baseline_dir=baseline_dir, candidate_dir=candidate_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "compare_json": output_dir / "compare.json",
        "compare_markdown": output_dir / "compare.md",
        "compare_html": output_dir / "compare.html",
    }
    write_json(paths["compare_json"], comparison)
    paths["compare_markdown"].write_text(render_compare_markdown(comparison), encoding="utf-8", newline="\n")
    paths["compare_html"].write_text(render_compare_html(comparison), encoding="utf-8", newline="\n")
    return {name: str(path) for name, path in paths.items()}


def build_run_comparison(*, baseline_dir: Path, candidate_dir: Path) -> dict[str, Any]:
    baseline = _read_run_dir(baseline_dir)
    candidate = _read_run_dir(candidate_dir)
    baseline_metrics = baseline["metrics"]
    candidate_metrics = candidate["metrics"]
    baseline_counts = dict(baseline_metrics.get("counts", {}))
    candidate_counts = dict(candidate_metrics.get("counts", {}))
    count_keys = sorted(set(baseline_counts) | set(candidate_counts))
    metric_keys = sorted((set(baseline_metrics) | set(candidate_metrics)) - {"counts"})
    baseline_cases = {str(row.get("case_id", "")): row for row in baseline["case_results"]}
    candidate_cases = {str(row.get("case_id", "")): row for row in candidate["case_results"]}
    case_ids = sorted((set(baseline_cases) | set(candidate_cases)) - {""})
    case_statuses = []
    for case_id in case_ids:
        baseline_row = baseline_cases.get(case_id)
        candidate_row = candidate_cases.get(case_id)
        baseline_status = baseline_row.get("status") if baseline_row else None
        candidate_status = candidate_row.get("status") if candidate_row else None
        case_statuses.append(
            {
                "case_id": case_id,
                "title": (candidate_row or baseline_row or {}).get("title", ""),
                "baseline_status": baseline_status,
                "candidate_status": candidate_status,
                "status_changed": baseline_status != candidate_status,
            }
        )

    return {
        "baseline": _run_summary(baseline_dir, baseline),
        "candidate": _run_summary(candidate_dir, candidate),
        "counts": {
            key: _delta_row(baseline_counts.get(key), candidate_counts.get(key))
            for key in count_keys
        },
        "metrics": {
            key: _delta_row(baseline_metrics.get(key), candidate_metrics.get(key))
            for key in metric_keys
        },
        "cases": {
            "total_compared": len(case_ids),
            "unchanged": sum(1 for row in case_statuses if not row["status_changed"]),
            "status_changed": sum(1 for row in case_statuses if row["status_changed"]),
            "added": sum(1 for row in case_statuses if row["baseline_status"] is None),
            "removed": sum(1 for row in case_statuses if row["candidate_status"] is None),
        },
        "case_statuses": case_statuses,
    }


def render_compare_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        f"# Enterprise Agent Range Compare: {comparison['baseline']['run_id']} vs {comparison['candidate']['run_id']}",
        "",
        "## Runs",
        "",
        f"- Baseline: `{comparison['baseline']['run_id']}` ({comparison['baseline']['path']})",
        f"- Candidate: `{comparison['candidate']['run_id']}` ({comparison['candidate']['path']})",
        "",
        "## Count Deltas",
        "",
        "| Count | Baseline | Candidate | Delta |",
        "|---|---:|---:|---:|",
    ]
    for key, row in comparison["counts"].items():
        lines.append(f"| {key} | {row['baseline']} | {row['candidate']} | {row['delta']} |")
    lines.extend(["", "## Metric Deltas", "", "| Metric | Baseline | Candidate | Delta |", "|---|---:|---:|---:|"])
    for key, row in comparison["metrics"].items():
        lines.append(f"| {key} | {row['baseline']} | {row['candidate']} | {row['delta']} |")
    lines.extend(
        [
            "",
            "## Case Status Changes",
            "",
            f"- Total compared: {comparison['cases']['total_compared']}",
            f"- Changed: {comparison['cases']['status_changed']}",
            f"- Added: {comparison['cases']['added']}",
            f"- Removed: {comparison['cases']['removed']}",
            "",
        ]
    )
    changed = [row for row in comparison["case_statuses"] if row["status_changed"]]
    if not changed:
        lines.append("- None")
    else:
        for row in changed[:100]:
            lines.append(
                f"- `{row['case_id']}` {row.get('title', '')}: "
                f"{row['baseline_status']} -> {row['candidate_status']}"
            )
        if len(changed) > 100:
            lines.append(f"- ... {len(changed) - 100} more")
    lines.append("")
    return "\n".join(lines)


def render_compare_html(comparison: dict[str, Any]) -> str:
    changed = [row for row in comparison["case_statuses"] if row["status_changed"]]
    counts_body = _comparison_rows(comparison["counts"])
    metrics_body = _comparison_rows(comparison["metrics"])
    if changed:
        changes_body = "\n".join(
            "<tr>"
            f"<td>{_html(row.get('case_id', ''))}</td>"
            f"<td>{_html(row.get('title', ''))}</td>"
            f"<td>{_html(row.get('baseline_status'))}</td>"
            f"<td>{_html(row.get('candidate_status'))}</td>"
            "</tr>"
            for row in changed[:100]
        )
        if len(changed) > 100:
            changes_body += f'\n<tr><td colspan="4">{_html(f"... {len(changed) - 100} more")}</td></tr>'
    else:
        changes_body = '<tr><td colspan="4">None</td></tr>'
    title = f"{comparison['baseline']['run_id']} vs {comparison['candidate']['run_id']}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Enterprise Agent Range Compare: {_html(title)}</title>
  <style>
    body {{ color: #1f2933; font-family: Arial, sans-serif; line-height: 1.5; margin: 2rem; }}
    h1, h2 {{ color: #102a43; }}
    table {{ border-collapse: collapse; margin: 1rem 0 2rem; width: 100%; }}
    th, td {{ border: 1px solid #bcccdc; padding: 0.5rem 0.65rem; text-align: left; vertical-align: top; }}
    th {{ background: #f0f4f8; }}
    code {{ background: #f0f4f8; padding: 0.1rem 0.25rem; }}
  </style>
</head>
<body>
  <h1>Enterprise Agent Range Compare: {_html(title)}</h1>
  <h2>Runs</h2>
  <table><tbody>
    <tr><th scope="row">Baseline</th><td><code>{_html(comparison['baseline']['run_id'])}</code> {_html(comparison['baseline']['path'])}</td></tr>
    <tr><th scope="row">Candidate</th><td><code>{_html(comparison['candidate']['run_id'])}</code> {_html(comparison['candidate']['path'])}</td></tr>
  </tbody></table>
  <h2>Count Deltas</h2>
  <table><thead><tr><th>Name</th><th>Baseline</th><th>Candidate</th><th>Delta</th></tr></thead><tbody>
{counts_body}
  </tbody></table>
  <h2>Metric Deltas</h2>
  <table><thead><tr><th>Name</th><th>Baseline</th><th>Candidate</th><th>Delta</th></tr></thead><tbody>
{metrics_body}
  </tbody></table>
  <h2>Case Status Changes</h2>
  <p>Total compared: {_html(comparison['cases']['total_compared'])}; changed: {_html(comparison['cases']['status_changed'])}; added: {_html(comparison['cases']['added'])}; removed: {_html(comparison['cases']['removed'])}.</p>
  <table>
    <thead><tr><th>Case ID</th><th>Title</th><th>Baseline</th><th>Candidate</th></tr></thead>
    <tbody>
{changes_body}
    </tbody>
  </table>
</body>
</html>
"""


def _read_run_dir(run_dir: Path) -> dict[str, Any]:
    return {
        "run_manifest": read_json(run_dir / "run-manifest.json"),
        "metrics": read_json(run_dir / "metrics.json"),
        "case_results": _read_jsonl(run_dir / "case-results.jsonl"),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _run_summary(run_dir: Path, run: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(run_dir),
        "run_id": run["run_manifest"].get("run_id", run_dir.name),
        "sut_id": run["run_manifest"].get("sut_id"),
        "sut_adapter": run["run_manifest"].get("sut_adapter"),
        "started_at": run["run_manifest"].get("started_at"),
    }


def _delta_row(baseline: Any, candidate: Any) -> dict[str, Any]:
    return {
        "baseline": baseline,
        "candidate": candidate,
        "delta": _numeric_delta(baseline, candidate),
    }


def _numeric_delta(baseline: Any, candidate: Any) -> int | float | None:
    if isinstance(baseline, bool) or isinstance(candidate, bool):
        return None
    if isinstance(baseline, (int, float)) and isinstance(candidate, (int, float)):
        return candidate - baseline
    return None


def _comparison_rows(rows: dict[str, dict[str, Any]]) -> str:
    if not rows:
        return '<tr><td colspan="4">None</td></tr>'
    return "\n".join(
        "<tr>"
        f"<th scope=\"row\">{_html(key)}</th>"
        f"<td>{_html(row.get('baseline'))}</td>"
        f"<td>{_html(row.get('candidate'))}</td>"
        f"<td>{_html(row.get('delta'))}</td>"
        "</tr>"
        for key, row in rows.items()
    )


def _html(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)
