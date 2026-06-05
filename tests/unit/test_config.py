from __future__ import annotations

from xa_guard.config import XAGuardConfig


def test_default_config_keeps_gate5_docker_disabled():
    cfg = XAGuardConfig()

    assert cfg.gate("gate5").enabled is False
