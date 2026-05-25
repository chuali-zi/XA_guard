"""国密 SM3 / SM2 接口封装。

策略（implementation-notes Q8）：
- 默认 SHA-256 / HMAC（demo 稳定）
- prefer_gm=True 尝试 gmssl；失败 → 自动 fallback + warn 日志
- 接口签名固定，便于 M5 阶段切换底层

子 agent 实施：
- sm3_hash(data) -> hex str
- sm2_sign(data, key_path) -> hex str
- sm2_verify(data, sig, pub_path) -> bool
- 不要 import gmssl 在模块顶层（按需 import 才能 fallback）
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from pathlib import Path

log = logging.getLogger("xa_guard.audit.sm_crypto")

_DEMO_HMAC_KEY = b"xa-guard-demo-hmac-key-2026"


def sm3_hash(data: bytes, *, prefer_gm: bool = False) -> str:
    """返回 hex 字符串。prefer_gm=True 时尝试 SM3，失败 fallback SHA-256。"""
    if prefer_gm:
        try:
            from gmssl import sm3, func  # type: ignore

            return sm3.sm3_hash(func.bytes_to_list(data))
        except Exception as exc:
            log.warning("SM3 unavailable, fallback to SHA-256: %s", exc)
    return hashlib.sha256(data).hexdigest()


def _read_key(key_path: str) -> bytes:
    """读密钥；不存在时返回 demo 默认 HMAC key（不抛异常以保证 demo 可跑）。"""
    if not key_path:
        return _DEMO_HMAC_KEY
    p = Path(key_path)
    if not p.exists():
        log.warning("key file not found: %s, fallback to demo HMAC key", key_path)
        return _DEMO_HMAC_KEY
    try:
        return p.read_bytes()
    except Exception as exc:
        log.warning("read key failed (%s), fallback demo HMAC key", exc)
        return _DEMO_HMAC_KEY


def sm2_sign(data: bytes, key_path: str = "", *, prefer_gm: bool = False) -> str:
    """SM2 签名（hex）。

    优先级：
    1. prefer_gm=True 且 gmssl 可用 → 尝试 SM2（占位：gmssl SM2 需 PEM 私钥，demo 不强求）
    2. fallback：HMAC-SHA256(key, data) → hex 字符串（demo 真实可验签）
    """
    if prefer_gm:
        try:
            from gmssl import sm2 as gm_sm2  # type: ignore

            # gmssl SM2 需要私钥 hex；这里只在 key_path 文件里第一行可读时尝试
            priv_hex = Path(key_path).read_text(encoding="utf-8").strip() if key_path else ""
            if priv_hex:
                sm2_crypt = gm_sm2.CryptSM2(public_key="", private_key=priv_hex)
                sig = sm2_crypt.sign(data, "0" * 64)  # 简化 nonce
                return sig
        except Exception as exc:
            log.warning("SM2 sign unavailable, fallback HMAC-SHA256: %s", exc)

    key = _read_key(key_path)
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def sm2_verify(data: bytes, sig: str, pub_path: str = "", *, prefer_gm: bool = False) -> bool:
    """SM2 验签；fallback HMAC-SHA256 常数时间比对。"""
    if prefer_gm:
        try:
            from gmssl import sm2 as gm_sm2  # type: ignore

            pub_hex = Path(pub_path).read_text(encoding="utf-8").strip() if pub_path else ""
            if pub_hex:
                sm2_crypt = gm_sm2.CryptSM2(public_key=pub_hex, private_key="")
                return bool(sm2_crypt.verify(sig, data))
        except Exception as exc:
            log.warning("SM2 verify unavailable, fallback HMAC: %s", exc)

    key = _read_key(pub_path)  # demo：对称密钥，对应同一份 key 文件
    expected = hmac.new(key, data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)
