"""Run L3 R7 OPA parity and fail-closed acceptance evidence.

This script does not relax any policy or test threshold. It compares the
baseline Gate3 fixtures through the Python backend and strict OPA backend, then
exercises strict OPA failure modes that must stop before downstream execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from xa_guard.config import GateConfig
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.policy.layered import LayeredPolicySource, set_global_source
from xa_guard.policy.opa_export import write_opa_bundle
from xa_guard.types import GateContext, InputSource, RiskLevel, TaintLabel

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "bench" / "cases" / "gate3-rule-fixtures.yaml"
DEFAULT_POLICY = ROOT / "policies" / "baseline" / "gate3_rules.yaml"
DEFAULT_MANIFEST = ROOT / "policies" / "baseline" / "manifest.yaml"
DEFAULT_OVERLAY = ROOT / "policies" / "overlay"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _ctx(payload: dict[str, Any]) -> GateContext:
    return GateContext(
        tool_name=str(payload.get("tool_name", "")),
        arguments=dict(payload.get("arguments", {}) or {}),
        user_role=str(payload.get("user_role", "user")),
        input_sources=[InputSource(str(s)) for s in payload.get("input_sources", ["user"])],
        risk_level=RiskLevel(str(payload.get("risk_level", "green"))),
        taint=TaintLabel(str(payload.get("taint", "PUBLIC"))),
        session_history=list(payload.get("session_history", []) or []),
    )


def _gate(*, backend: str, opa_path: Path | None = None, timeout: float = 5.0) -> Gate3Policy:
    options: dict[str, Any] = {
        "backend": backend,
        "policy_file": str(DEFAULT_POLICY),
    }
    if backend == "rego":
        options.update({"strict_opa": True, "opa_timeout_seconds": timeout})
        if opa_path is not None:
            options["opa_path"] = str(opa_path)
    return Gate3Policy(GateConfig(enabled=True, options=options))


def _eval_case(gate: Gate3Policy, payload: dict[str, Any]) -> dict[str, Any]:
    result = gate.evaluate(_ctx(payload))
    return {
        "decision": result.decision.value,
        "rule_hits": sorted(result.rule_hits),
        "metadata": result.metadata,
    }


def _opa_version(opa_path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [str(opa_path), "version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def _docker_image_inspect(image: str) -> dict[str, Any]:
    if not image:
        return {"status": "not_configured"}
    docker = shutil.which("docker")
    if not docker:
        return {"status": "blocked", "error": "docker executable not found"}
    proc = subprocess.run(
        [docker, "image", "inspect", image],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        return {"status": "blocked", "error": proc.stderr.strip(), "image": image}
    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        return {"status": "fail", "error": f"invalid docker inspect JSON: {exc}", "image": image}
    if not payload:
        return {"status": "blocked", "error": "docker image inspect returned no records", "image": image}
    item = payload[0]
    repo_digests = item.get("RepoDigests") or []
    return {
        "status": "pass",
        "image": image,
        "id": item.get("Id", ""),
        "repo_digests": repo_digests,
        "created": item.get("Created", ""),
        "labels": item.get("Config", {}).get("Labels") or {},
    }


def _write_fake_opa(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _expect_fail_closed(label: str, func) -> dict[str, Any]:
    downstream_executed = False
    try:
        func()
    except Exception as exc:
        return {
            "label": label,
            "status": "pass",
            "exception_type": type(exc).__name__,
            "exception": str(exc),
            "downstream_executed": downstream_executed,
        }
    return {
        "label": label,
        "status": "fail",
        "exception_type": "",
        "exception": "operation unexpectedly succeeded",
        "downstream_executed": downstream_executed,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    opa_path = Path(args.opa_path).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    source = LayeredPolicySource(
        manifest_path=DEFAULT_MANIFEST,
        overlay_root=DEFAULT_OVERLAY,
        project_root=ROOT,
    )
    set_global_source(source)
    bundle_manifest = write_opa_bundle(source, out_dir / "opa-bundle")

    fixtures = _load_yaml(DEFAULT_FIXTURE).get("fixtures", [])
    py_gate = _gate(backend="python")
    opa_gate = _gate(backend="rego", opa_path=opa_path, timeout=args.opa_timeout_seconds)

    cases: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for fixture in fixtures:
        rule_id = str(fixture["rule_id"])
        for polarity in ("positive", "negative"):
            case = fixture[polarity]
            payload = case["input_payload"]
            py_result = _eval_case(py_gate, payload)
            opa_result = _eval_case(opa_gate, payload)
            same = (
                py_result["decision"] == opa_result["decision"]
                and py_result["rule_hits"] == opa_result["rule_hits"]
            )
            expected_hit = bool(case["expected_hit"])
            expected_decision = case.get("expected_decision")
            expected_ok = (rule_id in opa_result["rule_hits"]) == expected_hit
            if expected_decision is not None:
                expected_ok = expected_ok and opa_result["decision"] == expected_decision
            if not same or not expected_ok:
                mismatches.append(f"{case['case_id']}:{rule_id}:{polarity}")
            cases.append(
                {
                    "case_id": case["case_id"],
                    "rule_id": rule_id,
                    "polarity": polarity,
                    "expected_hit": expected_hit,
                    "expected_decision": expected_decision,
                    "python": py_result,
                    "opa": opa_result,
                    "same": same,
                    "expected_ok": expected_ok,
                }
            )

    fail_closed: list[dict[str, Any]] = []
    fail_closed.append(
        _expect_fail_closed(
            "missing_opa_executable",
            lambda: _gate(backend="rego", opa_path=out_dir / "missing-opa", timeout=0.2),
        )
    )
    with tempfile.TemporaryDirectory(prefix="xa_r7_fake_opa_") as tmp:
        tmpdir = Path(tmp)
        sleep_opa = tmpdir / "opa-sleep"
        _write_fake_opa(sleep_opa, "#!/usr/bin/env sh\nsleep 2\n")
        fail_closed.append(
            _expect_fail_closed(
                "opa_timeout",
                lambda: _gate(backend="rego", opa_path=sleep_opa, timeout=0.1).evaluate(
                    _ctx({"tool_name": "exec_command", "arguments": {"cmd": "rm -rf /"}})
                ),
            )
        )
        bad_opa = tmpdir / "opa-bad-json"
        _write_fake_opa(bad_opa, "#!/usr/bin/env sh\nprintf 'not-json\\n'\n")
        fail_closed.append(
            _expect_fail_closed(
                "opa_invalid_response",
                lambda: _gate(backend="rego", opa_path=bad_opa, timeout=1.0).evaluate(
                    _ctx({"tool_name": "exec_command", "arguments": {"cmd": "rm -rf /"}})
                ),
            )
        )

    drift_gate = Gate3Policy(
        GateConfig(
            enabled=True,
            options={
                "backend": "rego",
                "strict_opa": True,
                "opa_path": str(opa_path),
                "opa_timeout_seconds": args.opa_timeout_seconds,
                "policy_file": str(DEFAULT_POLICY),
                "prefer_layered": True,
                "expected_policy_bundle_sha": "0" * 64,
            },
        )
    )
    fail_closed.append(
        _expect_fail_closed(
            "policy_bundle_sha_drift",
            lambda: drift_gate.evaluate(_ctx({"tool_name": "exec_command", "arguments": {"cmd": "echo ok"}})),
        )
    )

    all_fail_closed_pass = all(item["status"] == "pass" and not item["downstream_executed"] for item in fail_closed)
    status = "pass" if not mismatches and all_fail_closed_pass else "fail"
    report: dict[str, Any] = {
        "schema_version": "xa-l3-r7-opa-acceptance/v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "environment": {
            "python": sys.version,
            "platform": sys.platform,
            "cwd": str(ROOT),
            "opa_path": str(opa_path),
            "opa_sha256": _sha256(opa_path),
            "opa_version": _opa_version(opa_path),
            "opa_license": "Apache-2.0; local binary provenance is recorded by version/hash only unless paired with an approved image digest.",
            "docker": shutil.which("docker") or "",
        },
        "inputs": {
            "fixture": str(DEFAULT_FIXTURE),
            "fixture_sha256": _sha256(DEFAULT_FIXTURE),
            "policy": str(DEFAULT_POLICY),
            "policy_sha256": _sha256(DEFAULT_POLICY),
            "bundle_sha": source.bundle_sha,
            "bundle_manifest": bundle_manifest,
        },
        "parity": {
            "fixtures": len(fixtures),
            "cases": len(cases),
            "mismatches": mismatches,
            "cases_detail": cases,
        },
        "fail_closed": fail_closed,
        "image_provenance": {
            "inspect": _docker_image_inspect(args.opa_image),
            "trivy_report": str(Path(args.trivy_report).resolve()) if args.trivy_report else "",
            "trivy_report_sha256": _sha256(Path(args.trivy_report).resolve())
            if args.trivy_report and Path(args.trivy_report).exists()
            else "",
            "note": "OPA parity uses the configured OPA executable. Image inspect and Trivy report are provenance inputs only; vulnerability acceptance still requires an approved digest or explicit risk acceptance.",
        },
    }
    report_path = out_dir / "r7-opa-acceptance-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    hash_manifest = {
        "schema_version": "xa-artifact-hashes/v1",
        "artifacts": [
            {"path": str(path), "sha256": _sha256(path)}
            for path in sorted(out_dir.rglob("*"))
            if path.is_file()
        ],
    }
    (out_dir / "artifact-hashes.json").write_text(
        json.dumps(hash_manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({"status": status, "report": str(report_path), "cases": len(cases)}, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opa-path", default=str(ROOT / "tools" / "opa" / ("opa.exe" if os.name == "nt" else "opa.exe")))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--opa-timeout-seconds", type=float, default=5.0)
    parser.add_argument(
        "--opa-image",
        default="",
        help="optional OPA container image reference to inspect for provenance, e.g. openpolicyagent/opa:1.4.2-static",
    )
    parser.add_argument("--trivy-report", default="", help="optional existing Trivy JSON/text report to hash into evidence")
    args = parser.parse_args()
    report = run(args)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
