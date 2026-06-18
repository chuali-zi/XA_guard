"""审批令牌签发/验签单测 —— 方向 2/4 审批闭环。

覆盖：happy path、参数被改（TOCTOU）、签名伪造、过期、缺令牌、
进程内 token 防重放，以及 pipeline.run_after_approval 在令牌无效时拒绝执行。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from xa_guard.approval import args_hash, issue_approval, verify_and_consume_approval, verify_approval
from xa_guard.config import GateConfig, XAGuardConfig
from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.gates.gate2_plan import Gate2Plan
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.gates.gate5_sandbox import Gate5Sandbox
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.pipeline import Pipeline
from xa_guard.types import Approval, Decision, GateContext


def _issue(args=None):
    return issue_approval(
        trace_id="t-1",
        tool_name="grant_permission",
        arguments=args if args is not None else {"user": "alice"},
        approver="ops-1",
        reason="ok",
    )


def test_issue_and_verify_happy_path():
    appr = _issue()
    assert appr.token and appr.approver == "ops-1" and appr.args_hash
    ok, why = verify_approval(appr, trace_id="t-1", tool_name="grant_permission", arguments={"user": "alice"})
    assert ok and why == "ok"


def test_verify_args_mismatch():
    appr = _issue({"user": "alice"})
    ok, why = verify_approval(appr, trace_id="t-1", tool_name="grant_permission", arguments={"user": "mallory"})
    assert not ok and why == "args_hash_mismatch"


def test_verify_bad_signature():
    appr = _issue()
    forged = Approval(
        approver=appr.approver, reason=appr.reason, args_hash=appr.args_hash,
        issued_at=appr.issued_at, expires_at=appr.expires_at, token="deadbeef",
    )
    ok, why = verify_approval(forged, trace_id="t-1", tool_name="grant_permission", arguments={"user": "alice"})
    assert not ok and why == "bad_signature"


def test_verify_wrong_tool_rejected():
    appr = _issue()
    ok, why = verify_approval(appr, trace_id="t-1", tool_name="delete_file", arguments={"user": "alice"})
    assert not ok and why == "bad_signature"  # payload 含 tool_name → 签名不匹配


def test_verify_expired():
    appr = _issue()
    future = datetime.now(timezone.utc) + timedelta(seconds=999)
    ok, why = verify_approval(
        appr, trace_id="t-1", tool_name="grant_permission", arguments={"user": "alice"}, now=future
    )
    assert not ok and why == "expired"


def test_verify_missing_token():
    ok, why = verify_approval(None, trace_id="t-1", tool_name="grant_permission", arguments={})
    assert not ok and why == "missing_approval_token"
    ok, why = verify_approval(
        Approval(approver="x"), trace_id="t-1", tool_name="grant_permission", arguments={}
    )
    assert not ok and why == "missing_approval_token"


def test_verify_and_consume_rejects_replay():
    appr = issue_approval(
        trace_id="consume-1",
        tool_name="pending_approval_op",
        arguments={"ticket": "PA-1"},
        approver="ops-1",
        reason="ok",
    )

    ok, why = verify_and_consume_approval(
        appr,
        trace_id="consume-1",
        tool_name="pending_approval_op",
        arguments={"ticket": "PA-1"},
    )
    assert ok and why == "ok"

    ok, why = verify_and_consume_approval(
        appr,
        trace_id="consume-1",
        tool_name="pending_approval_op",
        arguments={"ticket": "PA-1"},
    )
    assert not ok and why == "approval_token_replay"


def test_args_hash_stable_regardless_of_key_order():
    assert args_hash({"a": 1, "b": 2}) == args_hash({"b": 2, "a": 1})


def _pipeline(tmp_path):
    cfg = XAGuardConfig()
    return Pipeline(
        gate1=Gate1Input(cfg.gate("gate1")),
        gate2=Gate2Plan(cfg.gate("gate2")),
        gate3=Gate3Policy(cfg.gate("gate3")),
        gate4=Gate4Taint(cfg.gate("gate4")),
        gate5=Gate5Sandbox(cfg.gate("gate5")),
        gate6=Gate6Audit(GateConfig(options={"audit_dir": str(tmp_path)})),
        cfg=cfg,
    )


def test_run_after_approval_denies_without_token(tmp_path):
    """REQUIRE_APPROVAL 后若没有有效令牌，run_after_approval 必须拒绝执行下游。"""
    pipeline = _pipeline(tmp_path)
    called = {"n": 0}

    async def executor(_ctx):
        called["n"] += 1
        return "should-not-run"

    async def run():
        ctx = GateContext(tool_name="grant_permission", arguments={"user": "alice"})
        ctx.final_decision = Decision.REQUIRE_APPROVAL  # 模拟已审批阻断态，但未挂 approval
        return await pipeline.run_after_approval(ctx, executor)

    res = asyncio.run(run())
    assert res.allowed is False
    assert "approval_token_invalid" in res.final_reason
    assert called["n"] == 0  # 下游绝不能被调用


def test_run_after_approval_denies_on_tampered_args(tmp_path):
    """审批后篡改入参（TOCTOU）→ args_hash 失配 → 拒绝执行。"""
    pipeline = _pipeline(tmp_path)
    called = {"n": 0}

    async def executor(_ctx):
        called["n"] += 1
        return "should-not-run"

    async def run():
        ctx = GateContext(tool_name="grant_permission", arguments={"user": "alice"})
        ctx.approval = issue_approval(
            trace_id=ctx.trace_id, tool_name="grant_permission",
            arguments={"user": "alice"}, approver="ops-1", reason="ok",
        )
        ctx.final_decision = Decision.REQUIRE_APPROVAL
        ctx.arguments = {"user": "mallory"}  # 篡改
        return await pipeline.run_after_approval(ctx, executor)

    res = asyncio.run(run())
    assert res.allowed is False
    assert "args_hash_mismatch" in res.final_reason
    assert called["n"] == 0


def test_run_after_approval_denies_replayed_token(tmp_path):
    """同一 approval token 在进程内只能驱动一次真实执行。"""
    pipeline = _pipeline(tmp_path)
    called = {"n": 0}

    async def executor(_ctx):
        called["n"] += 1
        return "ran"

    async def run():
        token = issue_approval(
            trace_id="replay-trace",
            tool_name="grant_permission",
            arguments={"user": "alice"},
            approver="ops-1",
            reason="ok",
        )
        first = GateContext(
            trace_id="replay-trace",
            tool_name="grant_permission",
            arguments={"user": "alice"},
        )
        first.approval = token
        first.final_decision = Decision.REQUIRE_APPROVAL
        first_result = await pipeline.run_after_approval(first, executor)

        replay = GateContext(
            trace_id="replay-trace",
            tool_name="grant_permission",
            arguments={"user": "alice"},
        )
        replay.approval = token
        replay.final_decision = Decision.REQUIRE_APPROVAL
        replay_result = await pipeline.run_after_approval(replay, executor)
        return first_result, replay_result

    first_result, replay_result = asyncio.run(run())
    assert first_result.allowed is True
    assert replay_result.allowed is False
    assert "approval_token_replay" in replay_result.final_reason
    assert called["n"] == 1
