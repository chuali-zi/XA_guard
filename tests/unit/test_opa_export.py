from __future__ import annotations

import json
import subprocess
from pathlib import Path

from xa_guard.policy.layered import LayeredPolicySource
from xa_guard.policy.opa_export import build_opa_data, write_opa_bundle

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_build_opa_data_exports_effective_layered_view():
    source = LayeredPolicySource(
        manifest_path="policies/baseline/manifest.yaml",
        overlay_root=None,
        project_root=PROJECT_ROOT,
    )

    data = build_opa_data(source)
    policy = data["xa_guard"]["policy"]

    assert policy["schema_version"] == "xa-guard-opa-policy-data/v0.1"
    assert policy["bundle_sha"] == source.bundle_sha
    assert len(policy["rules"]) == source.stats()["merged_rules"]
    assert policy["tool_risks"]["exec_command"] == "red"
    assert "exec_command" in policy["tool_capabilities"]
    assert policy["sensitive_patterns"]


def test_write_opa_bundle_writes_data_rego_and_manifest(tmp_path: Path):
    source = LayeredPolicySource(
        manifest_path="policies/baseline/manifest.yaml",
        overlay_root=None,
        project_root=PROJECT_ROOT,
    )

    manifest = write_opa_bundle(source, tmp_path)

    data_path = tmp_path / "data.json"
    rego_path = tmp_path / "gate3.rego"
    manifest_path = tmp_path / "manifest.json"

    assert data_path.exists()
    assert rego_path.exists()
    assert manifest_path.exists()
    assert manifest["bundle_sha"] == source.bundle_sha
    assert "hit contains" in rego_path.read_text(encoding="utf-8")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    assert data["xa_guard"]["policy"]["stats"]["merged_rules"] == source.stats()["merged_rules"]


def test_export_opa_policy_cli_smoke(tmp_path: Path):
    out_dir = tmp_path / "opa-bundle"
    proc = subprocess.run(
        ["python", "scripts/export_opa_policy.py", "--out-dir", str(out_dir)],
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(proc.stdout)
    assert payload["schema_version"] == "xa-guard-opa-bundle-manifest/v0.1"
    assert (out_dir / "data.json").exists()
    assert (out_dir / "gate3.rego").exists()
    assert (out_dir / "manifest.json").exists()
