from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
KIND = ROOT / "deploy" / "kind"
CHART = ROOT / "deploy" / "helm" / "xa-guard"


def _helm() -> str:
    configured = os.environ.get("HELM_BIN", "")
    if configured and Path(configured).exists():
        return configured
    value = shutil.which("helm")
    if not value:
        pytest.skip("Helm binary is not available")
    return value


def _config(*extra: str) -> dict[str, str]:
    rendered = subprocess.run(
        [_helm(), "template", "takeover", str(CHART), *extra],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    documents = [item for item in yaml.safe_load_all(rendered) if item]
    return next(item["data"] for item in documents if item["kind"] == "ConfigMap")


def test_effect_id_validator_matches_the_runtime_identifier() -> None:
    sys.path.insert(0, str(KIND))
    try:
        module = importlib.import_module("ha_runner")
        assert module.validate_effect_id("eff-" + "a" * 32) == "eff-" + "a" * 32
        with pytest.raises(ValueError, match="eff-"):
            module.validate_effect_id("00000000-0000-0000-0000-000000000000")
    finally:
        sys.path.remove(str(KIND))


def test_kind_proxy_rewrites_host_loopback_for_node_containers() -> None:
    sys.path.insert(0, str(KIND))
    try:
        module = importlib.import_module("ha_runner")
        result = module.kind_proxy_environment(
            {
                "HTTP_PROXY": "http://127.0.0.1:7897",
                "https_proxy": "http://localhost:7897",
                "NO_PROXY": "localhost,127.0.0.1",
            }
        )
    finally:
        sys.path.remove(str(KIND))
    assert result["HTTP_PROXY"] == "http://host.docker.internal:7897"
    assert result["https_proxy"] == "http://host.docker.internal:7897"
    assert result["NO_PROXY"].endswith(",host.docker.internal")


def test_fault_hooks_render_false_in_production_and_true_only_in_reference() -> None:
    assert _config()["XA_GUARD_TEST_FAULTS"] == "false"
    reference = _config(
        "--set",
        "referenceInfra.enabled=true",
        "--set",
        "referenceInfra.testFaults=true",
        "--set-string",
        "global.oidc.issuer=http://localhost:23081/realms/xa-guard",
        "--set-string",
        "global.kms.endpoint=http://host.docker.internal:23083",
    )
    assert reference["XA_GUARD_DEPLOYMENT_PROFILE"] == "reference"
    assert reference["XA_GUARD_TEST_FAULTS"] == "true"


def test_complete_takeover_command_plan_is_not_marked_incomplete() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(KIND / "ha_runner.py"),
            "accept",
            "--dry-run",
            "--prepare-takeover",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "HA evidence:" in result.stdout
