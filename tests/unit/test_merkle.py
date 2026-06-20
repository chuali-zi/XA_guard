"""ChainStore + compute_record_hash 单元测试。"""
from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path

from xa_guard.audit.merkle import ChainStore, canonical_json, compute_record_hash


def _multiprocess_append(path: str, prefix: str, count: int) -> None:
    store = ChainStore(path)
    for index in range(count):
        store.append({"trace_id": f"{prefix}-{index}"})


def _crash_while_holding_lock(path: str, ready) -> None:
    store = ChainStore(path)
    with store._append_lock():
        ready.set()
        os._exit(23)


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


def test_chainstore_append_refreshes_last_hash_across_instances(tmp_path: Path):
    p = tmp_path / "audit.jsonl"
    c1 = ChainStore(p)
    c2 = ChainStore(p)

    r1 = c1.append({"trace_id": "t1"})
    r2 = c2.append({"trace_id": "t2"})

    assert r2["gen_ai.evidence.hash_prev"] == r1["record_hash"]
    ok, idx = ChainStore(p).verify()
    assert ok is True
    assert idx is None


def test_chainstore_reuses_cached_tail_until_external_change(tmp_path: Path, monkeypatch):
    p = tmp_path / "audit.jsonl"
    c1 = ChainStore(p)
    recoveries = 0
    original = c1._recover_last_hash

    def counted_recovery():
        nonlocal recoveries
        recoveries += 1
        original()

    monkeypatch.setattr(c1, "_recover_last_hash", counted_recovery)
    first = c1.append({"trace_id": "t1"})
    second = c1.append({"trace_id": "t2"})
    assert recoveries == 0
    assert second["gen_ai.evidence.hash_prev"] == first["record_hash"]

    external = ChainStore(p).append({"trace_id": "external"})
    final = c1.append({"trace_id": "t3"})
    assert recoveries == 1
    assert final["gen_ai.evidence.hash_prev"] == external["record_hash"]
    assert c1.verify() == (True, None)


def test_chainstore_signs_before_single_append_and_fails_atomically(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    store = ChainStore(path)
    signed = store.append(
        {"trace_id": "signed"},
        signer=lambda payload: f"sig:{len(payload)}",
    )

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted == signed
    assert persisted["signature"].startswith("sig:")
    assert store.verify() == (True, None)

    def fail_signing(_payload: bytes) -> str:
        raise RuntimeError("signing unavailable")

    before = path.read_bytes()
    try:
        store.append({"trace_id": "must-not-appear"}, signer=fail_signing)
    except RuntimeError as exc:
        assert str(exc) == "signing unavailable"
    else:
        raise AssertionError("signer failure must propagate")
    assert path.read_bytes() == before


def test_chainstore_multiprocess_writers_preserve_chain(tmp_path: Path):
    path = tmp_path / "multiprocess.jsonl"
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=_multiprocess_append, args=(str(path), f"p{index}", 20))
        for index in range(4)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(30)
        assert process.exitcode == 0

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 80
    assert len({record["trace_id"] for record in records}) == 80
    assert ChainStore(path).verify() == (True, None)


def test_chainstore_os_lock_releases_when_owner_crashes(tmp_path: Path):
    path = tmp_path / "crash.jsonl"
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    process = context.Process(target=_crash_while_holding_lock, args=(str(path), ready))
    process.start()
    assert ready.wait(10)
    process.join(10)
    assert process.exitcode == 23

    appended = ChainStore(path).append({"trace_id": "after-crash"})
    assert appended["gen_ai.evidence.hash_prev"] == ""
    assert ChainStore(path).verify() == (True, None)


def test_chainstore_refuses_to_continue_after_corrupt_tail(tmp_path: Path):
    path = tmp_path / "corrupt.jsonl"
    path.write_text('{"trace_id":"partial"', encoding="utf-8")

    try:
        ChainStore(path)
    except RuntimeError as exc:
        assert "cannot recover audit chain tail" in str(exc)
    else:
        raise AssertionError("corrupt audit tail must fail closed")


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
