from __future__ import annotations

from pathlib import Path

from xa_guard.config import XAGuardConfig


def test_default_config_keeps_gate5_docker_disabled():
    cfg = XAGuardConfig()

    assert cfg.gate("gate5").enabled is False


def test_repository_config_enables_spotlighting_by_default():
    cfg = XAGuardConfig.from_yaml(Path("configs") / "xa-guard.yaml")

    assert cfg.gate("gate1").options["spotlighting"]["enabled"] is True
