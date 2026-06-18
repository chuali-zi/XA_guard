"""国密 SM3 / SM2 接口封装。

策略（implementation-notes Q8）：
- 默认 SHA-256 / HMAC（demo 稳定）
- prefer_gm=True 时返回**真实 SM3**：优先 gmssl，失败回退到内置纯 Python SM3
  （GB/T 32905-2016 标准实现，无第三方依赖），**不再静默降级为 SHA-256**，
  避免"标 sm3 实际 sha256"的伪加密隐患。
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


# --- 纯 Python SM3（GB/T 32905-2016）---------------------------------------
# 仅用标准库实现，保证无 gmssl 环境下也能产出真实 SM3 摘要，而非降级 SHA-256。
# 实现严格对照 gmssl 参考实现与 GB/T 32905-2016；标准测试向量：
#   sm3(b"")   == 1ab21d8355cfa17f8e61194831e81a8f22bec8c728fefb747ed035eb5082aa2b
#   sm3(b"abc")== 66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0

_SM3_IV = [
    0x7380166F, 0x4914B2B9, 0x172442D7, 0xDA8A0600,
    0xA96F30BC, 0x163138AA, 0xE38DEE4D, 0xB0FB0E4E,
]
_MASK = 0xFFFFFFFF


def _rotl32(x: int, n: int) -> int:
    n &= 31
    return ((x << n) | (x >> (32 - n))) & _MASK


def _ff_j(x: int, y: int, z: int, j: int) -> int:
    return (x ^ y ^ z) if j < 16 else ((x & y) | (x & z) | (y & z))


def _gg_j(x: int, y: int, z: int, j: int) -> int:
    return (x ^ y ^ z) if j < 16 else ((x & y) | (~x & _MASK & z))


def _p0(x: int) -> int:
    return x ^ _rotl32(x, 9) ^ _rotl32(x, 17)


def _p1(x: int) -> int:
    return x ^ _rotl32(x, 15) ^ _rotl32(x, 23)


def _sm3_pure(data: bytes) -> str:
    """纯 Python SM3 哈希（GB/T 32905-2016），返回 hex 字符串。"""
    # 1. 消息填充：补 1 位 + 0 + 64 位大端长度
    msg_len_bits = (len(data) * 8) & 0xFFFFFFFFFFFFFFFF
    padded = data + b"\x80"
    while len(padded) % 64 != 56:
        padded += b"\x00"
    padded += msg_len_bits.to_bytes(8, "big")

    v = list(_SM3_IV)
    # 常量 T_j：j in [0,16) -> 0x79CC4519 ; j in [16,64) -> 0x7A879D8A（GB/T 32905-2016）
    t_j = [0x79CC4519 if j < 16 else 0x7A879D8A for j in range(64)]

    for block_start in range(0, len(padded), 64):
        block = padded[block_start:block_start + 64]
        w = [int.from_bytes(block[i:i + 4], "big") for i in range(0, 64, 4)]
        for j in range(16, 68):
            w.append((_p1(w[j - 16] ^ w[j - 9] ^ _rotl32(w[j - 3], 15)) ^ _rotl32(w[j - 13], 7) ^ w[j - 6]) & _MASK)
        w1 = [w[j] ^ w[j + 4] for j in range(64)]

        a, b, c, d, e, f, g, h = v
        for j in range(64):
            ss1 = _rotl32((_rotl32(a, 12) + e + _rotl32(t_j[j], j % 32)) & _MASK, 7)
            ss2 = (ss1 ^ _rotl32(a, 12)) & _MASK
            tt1 = (_ff_j(a, b, c, j) + d + ss2 + w1[j]) & _MASK
            tt2 = (_gg_j(e, f, g, j) + h + ss1 + w[j]) & _MASK
            d, c, b = c, _rotl32(b, 9), a
            a = tt1
            h, g, f = g, _rotl32(f, 19), e
            e = _p0(tt2)
        v = [(x ^ y) & _MASK for x, y in zip(v, (a, b, c, d, e, f, g, h))]

    return "".join(f"{x:08x}" for x in v)


def sm3_hash(data: bytes, *, prefer_gm: bool = False) -> str:
    """返回 hex 字符串。

    prefer_gm=True 时返回真实 SM3：优先 gmssl，失败回退内置纯 Python SM3
    （GB/T 32905-2016），不再降级为 SHA-256，避免伪加密。
    prefer_gm=False 时返回 SHA-256（默认 demo 稳定口径）。
    """
    if prefer_gm:
        try:
            from gmssl import sm3, func  # type: ignore

            return sm3.sm3_hash(func.bytes_to_list(data))
        except Exception as exc:
            log.info("gmssl unavailable, using built-in pure-Python SM3 (GB/T 32905): %s", exc)
        return _sm3_pure(data)
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
