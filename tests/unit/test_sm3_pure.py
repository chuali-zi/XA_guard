"""纯 Python SM3（GB/T 32905-2016）单测。

锁定：
- `sm3_hash(prefer_gm=True)` 在无 gmssl 环境下也产出**真实 SM3**，不再降级 SHA-256
  （避免"标 sm3 实际 sha256"的伪加密隐患）。
- `_sm3_pure` 与 GB/T 32905-2016 标准测试向量一致。
- 若本机安装了 gmssl，`_sm3_pure` 与 gmssl 口径一致。
- SM3 哈希链（ChainStore algo="sm3"）可写、可验链，且记录哈希是真实 SM3 而非 SHA-256。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from xa_guard.audit.merkle import ChainStore, compute_record_hash
from xa_guard.audit.sm_crypto import _sm3_pure, sm3_hash

# GB/T 32905-2016 标准测试向量（权威：空串与单块 abc）
GBT_VECTORS = {
    b"": "1ab21d8355cfa17f8e61194831e81a8f22bec8c728fefb747ed035eb5082aa2b",
    b"abc": "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0",
}


def test_sm3_pure_matches_gbt_32905_standard_vectors() -> None:
    for msg, expected in GBT_VECTORS.items():
        assert _sm3_pure(msg) == expected, f"SM3({msg!r}) mismatch vs GB/T 32905-2016"


def test_sm3_pure_matches_gmssl_if_installed() -> None:
    gmssl = pytest.importorskip("gmssl")  # 本机无 gmssl 时 skip，不阻断
    from gmssl import func, sm3  # type: ignore

    cases = [b"", b"abc", b"abcd" * 16, b"a" * 1000, bytes(range(256)), b"\xff" * 128]
    for msg in cases:
        assert _sm3_pure(msg) == sm3.sm3_hash(func.bytes_to_list(msg)), f"divergence on {msg!r}"


def test_sm3_hash_prefer_gm_returns_real_sm3_not_sha256() -> None:
    """prefer_gm=True 必须返回真实 SM3，绝不能静默降级为 SHA-256（伪加密红线）。"""
    msg = b"xa-guard audit chain record"
    got = sm3_hash(msg, prefer_gm=True)
    assert got == _sm3_pure(msg), "prefer_gm=True should yield real SM3 (gmssl or pure-python)"
    assert got != hashlib.sha256(msg).hexdigest(), "must NOT silently fall back to SHA-256"


def test_sm3_pure_deterministic_and_distinct_from_sha256() -> None:
    msg = b"determinism check"
    assert _sm3_pure(msg) == _sm3_pure(msg)
    assert len(_sm3_pure(msg)) == 64  # 256-bit hex
    assert _sm3_pure(msg) != hashlib.sha256(msg).hexdigest()
    assert _sm3_pure(b"a") != _sm3_pure(b"b")


def test_sm3_hash_chain_writes_and_verifies(tmp_path: Path) -> None:
    """SM3 哈希链可写、可验链，记录哈希是真实 SM3。"""
    store = ChainStore(tmp_path / "audit.jsonl", algo="sm3")
    rec1 = {"trace_id": "t1", "event": "a", "gen_ai.evidence.hash_prev": ""}
    rec2 = {"trace_id": "t2", "event": "b", "gen_ai.evidence.hash_prev": ""}
    store.append(rec1)
    store.append(rec2)

    ok, err = store.verify()
    assert ok, f"SM3 chain verify failed: {err}"

    # 记录哈希应等于真实 SM3，而非 SHA-256
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    import json

    r1 = json.loads(lines[0])
    expected_sm3 = compute_record_hash(r1, algo="sm3")
    assert r1["record_hash"] == expected_sm3
    assert r1["record_hash"] != hashlib.sha256(
        json.dumps({k: v for k, v in r1.items() if k not in ("record_hash", "signature")}, sort_keys=True).encode()
    ).hexdigest()
