"""审批令牌（approval_token）签发与验签 —— 赛题方向 2/4 审批闭环。

设计目标：让"谁、在什么时候、对哪一组精确入参、批准了哪个工具、有效到何时"
成为可验证、可审计、不可事后伪造的证据，并且**令牌必须验签通过工具才会执行**
（不是审计里的装饰字段）。

令牌 = HMAC-SHA256(secret, canonical_json(payload))，payload 绑定：
    trace_id + tool_name + args_hash + approver + issued_at + expires_at

- args_hash 绑定精确入参 → 审批后篡改参数（TOCTOU）会令牌失配。
- expires_at → 过期令牌不可执行。
- secret 走环境变量 XA_GUARD_APPROVAL_SECRET（缺省 demo 密钥）。

demo 用 HMAC；生产可替换为 SM2/RSA 非对称签名，接口保持不变。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone

from xa_guard.types import Approval

_DEFAULT_SECRET = "xa-guard-demo-approval-secret"
_DEFAULT_TTL_SECONDS = 300


def _secret() -> bytes:
    return os.environ.get("XA_GUARD_APPROVAL_SECRET", _DEFAULT_SECRET).encode("utf-8")


def args_hash(arguments: dict | None) -> str:
    """对工具入参做 canonical sha256，绑定审批与精确参数。"""
    payload = json.dumps(
        arguments or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _payload(*, trace_id: str, tool_name: str, ah: str, approver: str, issued_at: str, expires_at: str) -> dict:
    return {
        "trace_id": trace_id,
        "tool_name": tool_name,
        "args_hash": ah,
        "approver": approver,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def _sign(payload: dict) -> str:
    msg = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hmac.new(_secret(), msg, hashlib.sha256).hexdigest()


def issue_approval(
    *,
    trace_id: str,
    tool_name: str,
    arguments: dict | None,
    approver: str,
    reason: str = "",
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> Approval:
    """在人工 approve 时签发令牌。"""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=ttl_seconds)
    ah = args_hash(arguments)
    issued_at = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    expires_at = exp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    token = _sign(_payload(
        trace_id=trace_id, tool_name=tool_name, ah=ah,
        approver=approver, issued_at=issued_at, expires_at=expires_at,
    ))
    return Approval(
        approver=approver,
        reason=reason,
        args_hash=ah,
        issued_at=issued_at,
        expires_at=expires_at,
        token=token,
    )


def verify_approval(
    approval: Approval | None,
    *,
    trace_id: str,
    tool_name: str,
    arguments: dict | None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """执行前验签：返回 (是否有效, 原因)。

    任一条件不满足即拒绝：缺令牌 / 参数失配 / 签名错误 / 过期。
    """
    if approval is None or not approval.token:
        return False, "missing_approval_token"
    ah = args_hash(arguments)
    if not hmac.compare_digest(ah, approval.args_hash or ""):
        return False, "args_hash_mismatch"
    expected = _sign(_payload(
        trace_id=trace_id, tool_name=tool_name, ah=approval.args_hash,
        approver=approval.approver, issued_at=approval.issued_at, expires_at=approval.expires_at,
    ))
    if not hmac.compare_digest(expected, approval.token):
        return False, "bad_signature"
    try:
        exp = datetime.strptime(approval.expires_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False, "bad_expiry"
    if (now or datetime.now(timezone.utc)) > exp:
        return False, "expired"
    return True, "ok"
