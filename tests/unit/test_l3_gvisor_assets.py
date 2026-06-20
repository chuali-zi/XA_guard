from __future__ import annotations

import json
from pathlib import Path

import yaml

from xa_guard.config import XAGuardConfig


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "gvisor"
COMPOSE = DEPLOY / "docker-compose.gvisor.yml"
PROFILE = ROOT / "configs" / "xa-guard.gvisor.yaml"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_gvisor_compose_override_is_hardened_and_rootless():
    services = _yaml(COMPOSE)["services"]
    guard = services["xa-guard"]
    helper = services["sandbox-image"]

    assert guard["runtime"] == helper["runtime"] == "runsc"
    assert "configs/xa-guard.gvisor.yaml" in guard["command"]
    assert guard["read_only"] is True
    assert guard["user"].startswith("${XA_GUARD_UID")
    assert guard["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in guard["security_opt"]
    assert guard["pids_limit"] > 0 and guard["mem_limit"] and guard["cpus"]
    assert any("${XDG_RUNTIME_DIR:" in volume for volume in guard["volumes"])
    assert not any("/var/run/docker.sock:/var/run/docker.sock" in volume for volume in guard["volumes"])

    assert helper["network_mode"] == "none"
    assert helper["read_only"] is True
    assert helper["user"] != "0:0"
    assert helper["pids_limit"] > 0 and helper["mem_limit"] and helper["cpus"]


def test_daemon_samples_register_runsc_without_changing_default_runtime():
    for name in ("daemon-system.json", "daemon-rootless.json"):
        daemon = json.loads((DEPLOY / name).read_text(encoding="utf-8"))
        assert daemon["default-runtime"] == "runc"
        assert daemon["runtimes"]["runsc"]["path"] == "/usr/local/bin/runsc"


def test_gvisor_application_profile_selects_isolated_runsc_children():
    raw = _yaml(PROFILE)["xa_guard"]
    gate5 = raw["gates"]["gate5"]
    expected = {
        "enabled": True,
        "docker_image": "xa-guard/sandbox:latest",
        "runtime": "runsc",
        "network_disabled": True,
        "readonly_rootfs": True,
        "memory": "256m",
        "cpus": "1",
        "pids_limit": 128,
        "sandbox_all_tools": True,
        "workspace_mount": False,
        "workspace_target": "/workspace",
        "workspace_readonly": True,
    }
    assert gate5 == expected

    parsed = XAGuardConfig.from_yaml(PROFILE)
    assert parsed.gate("gate5").options["runtime"] == "runsc"
    assert parsed.upstream.transport == "streamable-http"
    assert parsed.downstream


def test_gvisor_runbook_covers_install_validation_limits_and_rollback():
    runbook = (DEPLOY / "README.md").read_text(encoding="utf-8").lower()
    for required in (
        "prerequisites and runsc installation",
        "sha-512",
        "rootless deployment",
        "docker compose",
        "--network none",
        "read-only",
        "rollback",
        "not proof",
    ):
        assert required in runbook
