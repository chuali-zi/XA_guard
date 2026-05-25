"""ChainStore + compute_record_hash 单元测试。"""
from __future__ import annotations

import json
from pathlib import Path

from xa_guard.audit.merkle import ChainStore, canonical_json, compute_record_hash


def test_compute_record_hash_excludes_self_and_signature():
    """record_hash / signature 字段不参与自身哈希计算。"""
    base = {"trace_id": "t1", "data": {"a": 1, "b": 2}}
    h0 = compute_record_hash(base)
    # 加上 record_hash / signature 后哈希不变（被剔除）
    h1 = compute_record_hash({**base, "record_hash": "fake", "signature": "x"})
    assert h0 == h1
    # canonical：dict 顺序不影响
    h2 = compute_record_hash({"data": {"b": 2, "a": 1}, "trace_id": "t1"})
    assert h0 == h2


def test_chainstore_append_links_hash_prev(tmp_path: Path):
    p = tmp_path / "audit.jsonl"
    c = ChainStore(p)
    r1 = c.append({"trace_id": "t1"})
    r2 = c.append({"trace_id": "t2"})
    r3 = c.append({"trace_id": "t3"})

    assert r1["gen_ai.evidence.hash_prev"] == ""
    assert r2["gen_ai.evidence.hash_prev"] == r1["record_hash"]
    assert r3["gen_ai.evidence.hash_prev"] == r2["record_hash"]

    ok, idx = c.verify()
    assert ok is True
    assert idx is None


def test_chainstore_recovers_last_hash_on_reopen(tmp_path: Path):
    p = tmp_path / "audit.jsonl"
    c = ChainStore(p)
    c.append({"trace_id": "t1"})
    r2 = c.append({"trace_id": "t2"})
    last = r2["record_hash"]

    # 重新打开 → _last_hash 恢复
    c2 = ChainStore(p)
    assert c2.last_hash == last
    # 继续 append，hash_prev 应等于上次最后哈希
    r3 = c2.append({"trace_id": "t3"})
    assert r3["gen_ai.evidence.hash_prev"] == last
    ok, _ = c2.verify()
    assert ok is True


def test_chainstore_verify_detects_tampering(tmp_path: Path):
    p = tmp_path / "audit.jsonl"
    c = ChainStore(p)
    c.append({"trace_id": "t1"})
    c.append({"trace_id": "t2"})
    c.append({"trace_id": "t3"})

    # 篡改第 2 行
    lines = p.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1])
    rec["trace_id"] = "tampered"
    lines[1] = canonical_json(rec).decode("utf-8")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, idx = c.verify()
    assert ok is False
    assert idx == 2


def test_canonical_json_sorted_keys_no_whitespace():
    b = canonical_json({"b": 2, "a": 1})
    assert b == b'{"a":1,"b":2}'
