from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from bench.metrics import compute
from bench.runner import run_suite
from xa_guard.config import GateConfig, XAGuardConfig
from xa_guard.gates import GateStage
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.types import Decision


def _suite(tmp_path: Path, *, dimension: str = "data_safety", tool: str = "echo") -> Path:
    path = tmp_path / "suite.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "cases": [
                    {
                        "case_id": "CASE-001",
                        "dimension": dimension,
                        "attack_type": "benign",
                        "input_payload": {"tool_name": tool, "arguments": {}},
                        "expected_decision": "allow",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _cfg(tmp_path: Path) -> XAGuardConfig:
    cfg = XAGuardConfig.from_yaml("configs/xa-guard.opencode-smoke.yaml")
    cfg.gates["gate6"].options["audit_dir"] = str(tmp_path / "audit")
    return cfg


def test_supply_chain_preflight_writes_traceable_gate6_record(tmp_path: Path) -> None:
    suite = tmp_path / "supply.yaml"
    suite.write_text(
        yaml.safe_dump(
            {
                "cases": [
                    {
                        "case_id": "SCM-LOCAL",
                        "dimension": "supply_chain",
                        "attack_type": "package_install",
                        "input_payload": {
                            "tool_name": "install_plugin",
                            "arguments": {"name": "requests", "version": "2.31.0"},
                        },
                        "expected_decision": "allow",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    [result] = asyncio.run(run_suite(suite, _cfg(tmp_path)))

    assert result.trace_id
    assert result.audit_written is True
    assert result.audit_complete is True
    assert result.audit_record_hash
    assert "AIBOM-GATEWAY" in result.rule_hits
    assert compute([result]).audit_completeness == 1.0


class _BrokenPipeline:
    def __init__(self, audit_dir: Path, *, audit_fails: bool = False) -> None:
        self.gate6 = Gate6Audit(GateConfig(options={"audit_dir": str(audit_dir)}))
        self.audit_fails = audit_fails

    async def run(self, _ctx, _executor):
        raise RuntimeError("pipeline unavailable")

    def finalize_preflight(self, ctx):
        if self.audit_fails:
            raise OSError("audit unavailable")
        ctx.append(self.gate6(ctx, GateStage.OUTBOUND))


def test_runner_pipeline_exception_is_fail_closed_and_separate_from_metrics(
    tmp_path: Path, monkeypatch
) -> None:
    broken = _BrokenPipeline(tmp_path / "audit")
    monkeypatch.setattr("xa_guard.server.build_pipeline", lambda _cfg: broken)

    [result] = asyncio.run(run_suite(_suite(tmp_path), XAGuardConfig()))
    metrics = compute([result])

    assert result.actual_decision == Decision.DENY
    assert result.passed is False
    assert result.infra_error is True
    assert result.infra_error_type == "RuntimeError"
    assert result.audit_written is True
    assert metrics.total == 1
    assert metrics.evaluated_total == 0
    assert metrics.infra_errors == 1
    assert metrics.audit_completeness == 1.0


def test_runner_gate6_failure_is_explicitly_unaudited(tmp_path: Path, monkeypatch) -> None:
    broken = _BrokenPipeline(tmp_path / "audit", audit_fails=True)
    monkeypatch.setattr("xa_guard.server.build_pipeline", lambda _cfg: broken)

    [result] = asyncio.run(run_suite(_suite(tmp_path), XAGuardConfig()))
    metrics = compute([result])

    assert result.actual_decision == Decision.DENY
    assert result.infra_error is True
    assert result.audit_written is False
    assert metrics.audit_missing == 1
    assert metrics.audit_completeness == 0.0
