from __future__ import annotations

from pathlib import Path

from xa_guard.config import XAGuardConfig


def test_default_config_keeps_gate5_docker_disabled():
    cfg = XAGuardConfig()

    assert cfg.gate("gate5").enabled is False


def test_repository_config_enables_spotlighting_by_default():
    cfg = XAGuardConfig.from_yaml(Path("configs") / "xa-guard.yaml")

    assert cfg.gate("gate1").options["spotlighting"]["enabled"] is True


def test_docker_config_uses_static_downstream_manifest_and_sandbox_all_tools():
    cfg = XAGuardConfig.from_yaml(Path("configs") / "xa-guard.docker.yaml")

    assert cfg.upstream.transport == "streamable-http"
    assert cfg.upstream.session_idle_timeout_seconds == 300
    assert cfg.gate("gate5").enabled is True
    assert cfg.gate("gate5").options["sandbox_all_tools"] is True
    assert cfg.gate("gate5").options["workspace_mount"] is False
    assert cfg.downstream
    assert cfg.downstream[0].name == "ops_target"
    assert {tool["name"] for tool in cfg.downstream[0].tools} >= {"get_cpu", "exec_command", "send_email"}


def test_streamable_http_idle_timeout_must_be_positive(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text(
        "xa_guard:\n  upstream:\n    transport: streamable-http\n    session_idle_timeout_seconds: 0\n",
        encoding="utf-8",
    )

    try:
        XAGuardConfig.from_yaml(path)
    except ValueError as exc:
        assert "session_idle_timeout_seconds must be positive" in str(exc)
    else:
        raise AssertionError("invalid session timeout was accepted")


def test_opencode_smoke_config_uses_safe_stdio_fixture_and_separate_audit_dir():
    cfg = XAGuardConfig.from_yaml(Path("configs") / "xa-guard.opencode-smoke.yaml")

    assert cfg.upstream.transport == "stdio"
    assert cfg.downstream[0].command == ["python", "-m", "demo.targets.ops_target"]
    assert cfg.gate("gate5").enabled is False
    assert cfg.gate("gate6").options["audit_dir"] == "./logs/opencode-smoke"
    assert cfg.gate("gate2").options["elicitation_fallback"] == "deny"
