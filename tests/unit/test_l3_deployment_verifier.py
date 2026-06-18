from __future__ import annotations

import argparse
from pathlib import Path

from scripts import verify_l3_deployment as verifier


def _args(tmp_path: Path, **overrides):
    values = {
        "compose_file": "docker-compose.yml",
        "config": "configs/xa-guard.docker.yaml",
        "output": str(tmp_path / "verify.json"),
        "health_url": "http://127.0.0.1:3000/healthz",
        "run_build": False,
        "run_up": False,
        "timeout": 1,
        "build_timeout": 1,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_l3_deployment_report_marks_docker_absence_as_blocked(monkeypatch, tmp_path):
    def fake_run(command, *, timeout=120):
        if command[:3] == ["docker", "compose", "-f"]:
            return {
                "command": command,
                "status": "pass",
                "exit_code": 0,
                "stdout_tail": "services: {}",
                "stderr_tail": "",
            }
        return {
            "command": command,
            "status": "fail",
            "exit_code": 1,
            "stdout_tail": "",
            "stderr_tail": "failed to connect to the docker API; is the daemon running?",
        }

    monkeypatch.setattr(verifier, "run_command", fake_run)

    report = verifier.build_report(_args(tmp_path))

    assert report["summary"]["status"] == "blocked_external_dependency"
    by_name = {step["name"]: step for step in report["steps"]}
    assert by_name["required_files"]["status"] == "pass"
    assert by_name["docker_version"]["status"] == "blocked"
    assert by_name["docker_version"]["blocker"] == "docker_daemon_unavailable"
    assert by_name["docker_compose_config"]["status"] == "pass"
    assert report["static"]["services"] == ["sandbox-image", "xa-guard"]
    assert "xa-guard/sandbox:latest" in report["static"]["images"]
    assert report["static"]["docker_socket_mounted"] is True
    assert report["static"]["healthcheck_present"] is True
    assert report["static"]["config_transport"] == "streamable-http"
    assert report["static"]["gate5_sandbox_all_tools"] is True
    assert report["file_inventory"]


def test_l3_deployment_report_runs_build_up_and_health_when_requested(monkeypatch, tmp_path):
    seen = []

    def fake_run(command, *, timeout=120):
        seen.append(command)
        return {
            "command": command,
            "status": "pass",
            "exit_code": 0,
            "stdout_tail": "ok",
            "stderr_tail": "",
        }

    monkeypatch.setattr(verifier, "run_command", fake_run)
    monkeypatch.setattr(
        verifier,
        "_health_check",
        lambda url, timeout=10: {"url": url, "status": "pass", "http_status": 200},
    )

    report = verifier.build_report(_args(tmp_path, run_build=True, run_up=True))

    assert report["summary"]["status"] == "pass"
    names = [step["name"] for step in report["steps"]]
    assert "docker_compose_build" in names
    assert "docker_compose_up" in names
    assert "healthz" in names
    assert any(command[:3] == ["docker", "compose", "-f"] for command in seen)


def test_l3_deployment_report_blocks_runtime_steps_without_docker(monkeypatch, tmp_path):
    def fake_run(command, *, timeout=120):
        if command[:3] == ["docker", "compose", "-f"]:
            return {
                "command": command,
                "status": "pass",
                "exit_code": 0,
                "stdout_tail": "services: {}",
                "stderr_tail": "",
            }
        return {
            "command": command,
            "status": "fail",
            "exit_code": 1,
            "stdout_tail": "",
            "stderr_tail": "Cannot connect to the Docker daemon. Is the docker daemon running?",
        }

    monkeypatch.setattr(verifier, "run_command", fake_run)

    report = verifier.build_report(_args(tmp_path, run_build=True, run_up=True))
    by_name = {step["name"]: step for step in report["steps"]}

    assert report["summary"]["status"] == "blocked_external_dependency"
    assert by_name["docker_compose_build"]["status"] == "blocked"
    assert by_name["docker_compose_build"]["blocker"] == "docker_daemon_unavailable"
    assert by_name["docker_compose_up"]["status"] == "blocked"
    assert by_name["docker_compose_up"]["blocker"] == "docker_daemon_unavailable"
    assert "healthz" not in by_name
