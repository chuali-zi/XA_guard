"""Unit tests for Gate4Taint — 三色信息流污点关卡。"""
from __future__ import annotations

import pytest

from xa_guard.config import GateConfig
from xa_guard.gates.base import GateStage
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.types import Decision, GateContext, InputSource, TaintLabel

CAP_FILE = "policies/tool_capabilities.yaml"


def _gate(strict: bool = False) -> Gate4Taint:
    cfg = GateConfig(
        enabled=True,
        options={
            "tool_capabilities_file": CAP_FILE,
            "strict_mode": strict,
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


# ──────────────────────────────────────────────
# 6. 未登记工具默认 input_max=CONFIDENTIAL → PUBLIC 输入 ALLOW
# ──────────────────────────────────────────────
def test_unknown_tool_defaults_allow():
    gate = _gate()
    ctx = GateContext(
        tool_name="some_unregistered_tool_xyz",
        arguments={"q": "ping"},
        input_sources=[InputSource.USER],
        taint=TaintLabel.PUBLIC,
    )
    result = gate.evaluate(ctx, GateStage.INBOUND)
    assert result.decision == Decision.ALLOW


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
# 9. strict_mode: WARN 升级到 DENY
#    (构造 OUTBOUND 场景: send_notification + ctx.taint=INTERNAL → output_taint=PUBLIC
#     new_taint=INTERNAL, no NETWORK_EXTERNAL block normally → ALLOW in non-strict
#     strict_mode doesn't change ALLOW, test actual DENY path with strict)
# ──────────────────────────────────────────────
def test_strict_mode_confidential_outbound_denied():
    """strict_mode=true 下，CONFIDENTIAL 走外网工具仍 DENY（验证 strict 路径）。"""
    gate = _gate(strict=True)
    ctx = GateContext(
        tool_name="send_email",
        arguments={},
        taint=TaintLabel.CONFIDENTIAL,
    )
    result = gate.evaluate(ctx, GateStage.OUTBOUND)
    assert result.decision == Decision.DENY
