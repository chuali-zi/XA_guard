"""Unit tests for Gate4Taint — 三色信息流污点关卡。"""
from __future__ import annotations

from pathlib import Path

import pytest

from xa_guard.config import GateConfig
from xa_guard.gates.base import GateStage
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.policy.layered import LayeredPolicySource, set_global_source
from xa_guard.types import Decision, GateContext, InputSource, TaintLabel

CAP_FILE = "policies/baseline/gate4_capabilities.yaml"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _isolate_layered_source():
    yield
    set_global_source(None)


def _gate(strict: bool = False) -> Gate4Taint:
    cfg = GateConfig(
        enabled=True,
        options={
            "tool_capabilities_file": CAP_FILE,
            "strict_mode": strict,
        },
    )
    return Gate4Taint(cfg)


def _layered_gate() -> Gate4Taint:
    set_global_source(
        LayeredPolicySource(
            manifest_path="policies/baseline/manifest.yaml",
            overlay_root=None,
            project_root=PROJECT_ROOT,
        )
    )
    cfg = GateConfig(
        enabled=True,
        options={
            "tool_capabilities_file": CAP_FILE,
            "prefer_layered": True,
        },
    )
    return Gate4Taint(cfg)


# ──────────────────────────────────────────────
# 1. PUBLIC 来源 → 任意已登记工具 ALLOW
# ──────────────────────────────────────────────
def test_public_source_allows_any_registered_tool():
    gate = _gate()
    ctx = GateContext(
        tool_name="send_email",
        arguments={"to": "ops@example.com", "body": "hello"},
        input_sources=[InputSource.USER],
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.ALLOW
    assert result.metadata["taint"] == "PUBLIC"


# ──────────────────────────────────────────────
# 2. arguments 含密钥 → CONFIDENTIAL → send_email DENY
#    (send_email.input_max_taint=INTERNAL < CONFIDENTIAL)
# ──────────────────────────────────────────────
def test_confidential_from_argument_denies_send_email():
    gate = _gate()
    ctx = GateContext(
        tool_name="send_email",
        arguments={"body": "access_key=AKIAIOSFODNN7EXAMPLE"},
        input_sources=[InputSource.USER],
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.DENY
    assert result.metadata["taint"] == "CONFIDENTIAL"
    assert any("CONFIDENTIAL" in r for r in result.risks)


@pytest.mark.parametrize(
    "body",
    [
        "手机号 13800138000",
        "银行卡 6222020000000000",
        "医疗健康 敏感个人信息",
        "金融账户 敏感个人信息",
        "行踪轨迹 敏感个人信息",
    ],
)
def test_confidential_from_chinese_sensitive_terms_denies_notification(body):
    gate = _gate()
    ctx = GateContext(
        tool_name="send_notification",
        arguments={"channel": "external_slack", "msg": body},
        input_sources=[InputSource.USER],
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.DENY
    assert result.metadata["taint"] == "CONFIDENTIAL"


# ──────────────────────────────────────────────
# 3. INTERNAL → post_url (input_max=PUBLIC) → DENY
# ──────────────────────────────────────────────
def test_internal_to_post_url_denied():
    gate = _gate()
    ctx = GateContext(
        tool_name="post_url",
        arguments={"url": "https://example.com"},
        input_sources=[InputSource.DOCUMENT],   # DOCUMENT → INTERNAL
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.DENY
    assert result.metadata["taint"] == "INTERNAL"


# ──────────────────────────────────────────────
# 4. INTERNAL → send_email (input_max=INTERNAL) → ALLOW
# ──────────────────────────────────────────────
def test_internal_to_send_email_allowed():
    gate = _gate()
    ctx = GateContext(
        tool_name="send_email",
        arguments={"to": "ops@example.com", "body": "log summary"},
        input_sources=[InputSource.DOCUMENT],
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.ALLOW
    assert result.metadata["taint"] == "INTERNAL"


# ──────────────────────────────────────────────
# 5. OUTBOUND: read_log (output_taint=INTERNAL) 升级 ctx.taint
# ──────────────────────────────────────────────
def test_outbound_read_log_upgrades_taint():
    gate = _gate()
    ctx = GateContext(
        tool_name="read_log",
        arguments={},
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.OUTBOUND)
    assert result.decision == Decision.ALLOW
    assert result.metadata["output_taint"] == "INTERNAL"


@pytest.mark.parametrize("tool_name", ["delete_file", "drop_table"])
def test_destructive_red_tools_have_explicit_capabilities(tool_name):
    gate = _gate()
    ctx = GateContext(tool_name=tool_name, arguments={}, taint=TaintLabel.PUBLIC)
    result = gate.evaluate(ctx, GateStage.INBOUND)
    cap = result.metadata["tool_capability"]
    assert cap["risk_level"] == "red"
    assert cap["capabilities"]


# ──────────────────────────────────────────────
# 6. 未登记工具 fail-closed：
#    6a. PUBLIC 来源 → ALLOW（input_max=PUBLIC，等级相等可流入）
#    6b. INTERNAL 来源 → DENY（input_max=PUBLIC，INTERNAL > PUBLIC，拒绝）
#    6c. OUTBOUND + unknown tool → CONFIDENTIAL 外发 DENY（capabilities 含 NETWORK_EXTERNAL）
# ──────────────────────────────────────────────
def test_unknown_tool_public_input_allows():
    """未登记工具 input_max_taint=PUBLIC，PUBLIC 来源仍 ALLOW（fail-closed 不过激）。"""
    gate = _gate()
    ctx = GateContext(
        tool_name="some_unregistered_tool_xyz",
        arguments={"q": "ping"},
        input_sources=[InputSource.USER],
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.ALLOW


def test_unknown_tool_internal_input_denied():
    """未登记工具 fail-closed：INTERNAL 数据流入未知工具 → DENY。"""
    gate = _gate()
    ctx = GateContext(
        tool_name="some_unregistered_tool_xyz",
        arguments={"q": "internal report"},
        input_sources=[InputSource.DOCUMENT],  # DOCUMENT → INTERNAL
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.DENY
    assert result.metadata["taint"] == "INTERNAL"


def test_unknown_tool_outbound_confidential_denied():
    """未登记工具 fail-closed：OUTBOUND 时 output_taint=CONFIDENTIAL + NETWORK_EXTERNAL → DENY。"""
    gate = _gate()
    ctx = GateContext(
        tool_name="some_unregistered_tool_xyz",
        arguments={},
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.OUTBOUND)
    assert result.decision == Decision.DENY
    assert any("CONFIDENTIAL" in r for r in result.risks)


# ──────────────────────────────────────────────
# 7. session_history 含敏感词 → CONFIDENTIAL 推断
# ──────────────────────────────────────────────
def test_session_history_sensitive_escalates_taint():
    gate = _gate()
    ctx = GateContext(
        tool_name="send_email",
        arguments={"body": "report"},
        input_sources=[InputSource.USER],
        taint=TaintLabel.PUBLIC,
        session_history=[{"role": "assistant", "content": "密码是 hunter2"}],
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.DENY
    assert result.metadata["taint"] == "CONFIDENTIAL"


def test_sensitive_argument_key_escalates_taint():
    gate = _gate()
    ctx = GateContext(
        tool_name="send_email",
        arguments={"password": "hunter2"},
        input_sources=[InputSource.USER],
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.DENY
    assert result.metadata["taint"] == "CONFIDENTIAL"


def test_layered_email_destination_does_not_escalate_payload_taint():
    gate = _layered_gate()
    ctx = GateContext(
        tool_name="send_email",
        arguments={"to": "ops@example.com", "body": "hello"},
        input_sources=[InputSource.USER],
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.ALLOW
    assert result.metadata["taint"] == "PUBLIC"


def test_layered_email_body_still_escalates_payload_taint():
    gate = _layered_gate()
    ctx = GateContext(
        tool_name="send_email",
        arguments={"to": "ops@example.com", "body": "contact: user@example.com"},
        input_sources=[InputSource.USER],
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.DENY
    assert result.metadata["taint"] == "CONFIDENTIAL"


@pytest.mark.parametrize(
    "arguments",
    [
        {"to": "AKIAIOSFODNN7EXAMPLE@example.com", "body": "hello"},
        {"recipient": "身份证 110105199001011234", "body": "hello"},
        {"channel": "secret_key=prod_12345678901234567890", "msg": "hello"},
    ],
)
def test_layered_routing_fields_still_scan_high_confidence_secrets(arguments):
    gate = _layered_gate()
    ctx = GateContext(
        tool_name="send_email",
        arguments=arguments,
        input_sources=[InputSource.USER],
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.DENY
    assert result.metadata["taint"] == "CONFIDENTIAL"


# ──────────────────────────────────────────────
# 8. OUTBOUND CONFIDENTIAL + NETWORK_EXTERNAL → DENY
# ──────────────────────────────────────────────
def test_outbound_confidential_external_tool_denied():
    gate = _gate()
    ctx = GateContext(
        tool_name="send_notification",
        arguments={},
        taint=TaintLabel.CONFIDENTIAL,
    )
    result = gate.evaluate(ctx, GateStage.OUTBOUND)
    assert result.decision == Decision.DENY
    assert any("CONFIDENTIAL" in r for r in result.risks)


# ──────────────────────────────────────────────
# 9. strict_mode 配置项兼容性验证：gate4 的 OUTBOUND 机密外泄本身直接 DENY（无 WARN 路径），
#    strict_mode=true 不改变决策结果，仅保留配置项读取兼容性。
# ──────────────────────────────────────────────
def test_strict_mode_confidential_outbound_denied():
    """strict_mode=true 时，CONFIDENTIAL 走外网工具仍 DENY（gate4 无 WARN 路径，直接 fail-closed）。"""
    gate = _gate(strict=True)
    ctx = GateContext(
        tool_name="send_email",
        arguments={},
        taint=TaintLabel.CONFIDENTIAL,
    )
    result = gate.evaluate(ctx, GateStage.OUTBOUND)
    assert result.decision == Decision.DENY
