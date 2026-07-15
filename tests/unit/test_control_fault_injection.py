from __future__ import annotations

import asyncio
import json

import pytest

from xa_guard.control.faults import FaultController


def _controller(monkeypatch, tmp_path) -> FaultController:
    monkeypatch.setenv("XA_GUARD_TEST_FAULTS", "true")
    monkeypatch.setenv("XA_GUARD_DEPLOYMENT_PROFILE", "reference")
    monkeypatch.setenv("XA_GUARD_TEST_FAULT_DIR", str(tmp_path))
    return FaultController()


def test_fault_markers_are_one_shot_and_record_reached(monkeypatch, tmp_path) -> None:
    controller = _controller(monkeypatch, tmp_path)
    (tmp_path / "crash-window").write_text("armed\n", encoding="utf-8")

    assert controller.consume("crash-window") == "armed"
    assert controller.consume("crash-window") is None
    assert (tmp_path / "reached-crash-window").read_text(encoding="utf-8").strip() == "reached"


def test_fault_plan_pops_steps_without_replaying(monkeypatch, tmp_path) -> None:
    controller = _controller(monkeypatch, tmp_path)
    path = tmp_path / "cancel_response_plan"
    path.write_text(
        json.dumps({"steps": [{"mode": "response", "status": 429}, {"mode": "normal"}]}),
        encoding="utf-8",
    )

    assert controller.next_step("cancel_response_plan") == {"mode": "response", "status": 429}
    assert controller.next_step("cancel_response_plan") == {"mode": "normal"}
    assert controller.next_step("cancel_response_plan") is None


def test_fault_delay_is_bounded(monkeypatch, tmp_path) -> None:
    controller = _controller(monkeypatch, tmp_path)
    (tmp_path / "short-delay").write_text("0.001", encoding="utf-8")

    assert asyncio.run(controller.delay_if_armed("short-delay")) is True


def test_production_rejects_fault_injection(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XA_GUARD_TEST_FAULTS", "true")
    monkeypatch.setenv("XA_GUARD_DEPLOYMENT_PROFILE", "production")
    monkeypatch.setenv("XA_GUARD_TEST_FAULT_DIR", str(tmp_path))

    with pytest.raises(RuntimeError, match="cannot be enabled in production"):
        FaultController()
