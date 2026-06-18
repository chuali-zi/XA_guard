"""真实 SM2 签名（GB/T 32918）单测。

锁定：
- `generate_sm2_keypair()` 产出合法 SM2 椭圆曲线密钥对（priv 64 hex / pub 128 hex）。
- `sm2_sign(prefer_gm=True)` 产出真实 SM2 签名（128 hex r||s），非 HMAC-SHA256（64 hex）。
- `sm2_verify(prefer_gm=True)` 对真实签名验通过，篡改数据/伪造签名验失败。
- keyfile 键值格式（private/public）与单行 hex 兼容性。
- gmssl 未安装时相关用例 skip（不阻断），prefer_gm=False 仍走 HMAC demo 路径。
"""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

import pytest

from xa_guard.audit.sm_crypto import (
    _load_sm2_keyfile,
    generate_sm2_keypair,
    sm2_sign,
    sm2_verify,
    write_sm2_keyfile,
)


def _need_gmssl():
    pytest.importorskip("gmssl")


def test_generate_sm2_keypair_produces_valid_curve_point() -> None:
    _need_gmssl()
    priv, pub = generate_sm2_keypair()
    assert len(priv) == 64
    assert len(pub) == 128
    int(priv, 16)  # hex
    int(pub, 16)  # hex
    # 公钥点不应是无穷远点（全零）
    assert pub != "0" * 128


def test_write_and_load_sm2_keyfile_roundtrip(tmp_path: Path) -> None:
    _need_gmssl()
    priv, pub = generate_sm2_keypair()
    kp = tmp_path / "sm2.key"
    write_sm2_keyfile(kp, priv, pub)
    loaded = _load_sm2_keyfile(str(kp))
    assert loaded["private"] == priv
    assert loaded["public"] == pub


def test_sm2_sign_verify_roundtrip_real_gm(tmp_path: Path) -> None:
    _need_gmssl()
    priv, pub = generate_sm2_keypair()
    kp = tmp_path / "sm2.key"
    write_sm2_keyfile(kp, priv, pub)
    data = b"xa-guard audit chain record payload"
    sig = sm2_sign(data, str(kp), prefer_gm=True)
    # 真实 SM2 签名是 128 hex (r||s)，不是 HMAC-SHA256 的 64 hex
    assert len(sig) == 128
    assert all(c in "0123456789abcdef" for c in sig)
    assert len(sig) != len(hashlib.sha256(data).hexdigest())
    assert sm2_verify(data, sig, str(kp), prefer_gm=True) is True


def test_sm2_verify_rejects_tampered_and_forged(tmp_path: Path) -> None:
    _need_gmssl()
    priv, pub = generate_sm2_keypair()
    kp = tmp_path / "sm2.key"
    write_sm2_keyfile(kp, priv, pub)
    data = b"original audit payload"
    sig = sm2_sign(data, str(kp), prefer_gm=True)
    assert sm2_verify(b"tampered payload", sig, str(kp), prefer_gm=True) is False
    assert sm2_verify(data, "a" * 128, str(kp), prefer_gm=True) is False


def test_sm2_sign_with_publickey_missing_derives_from_private(tmp_path: Path) -> None:
    """keyfile 只含 private 时签名仍可用（公钥从私钥推导）。"""
    _need_gmssl()
    priv, pub = generate_sm2_keypair()
    kp = tmp_path / "priv_only.key"
    # 只写 private 行
    kp.write_text(f"private: {priv}\n", encoding="utf-8")
    data = b"payload for private-only keyfile"
    sig = sm2_sign(data, str(kp), prefer_gm=True)
    assert len(sig) == 128
    # 用完整 keyfile（含 pub）验签应通过
    full = tmp_path / "full.key"
    write_sm2_keyfile(full, priv, pub)
    assert sm2_verify(data, sig, str(full), prefer_gm=True) is True


def test_sm2_prefer_gm_false_uses_hmac_demo_path(tmp_path: Path) -> None:
    """prefer_gm=False 走 HMAC-SHA256 demo 路径（保持向后兼容）。"""
    key = tmp_path / "demo.key"
    key.write_bytes(b"demo-secret-key")
    data = b"demo payload"
    sig = sm2_sign(data, str(key), prefer_gm=False)
    assert sig == hmac.new(b"demo-secret-key", data, hashlib.sha256).hexdigest()
    assert sm2_verify(data, sig, str(key), prefer_gm=False) is True
