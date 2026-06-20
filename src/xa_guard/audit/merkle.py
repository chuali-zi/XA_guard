"""审计哈希链 / 简化 Merkle。

设计：
- 每条审计记录的 record_hash = hash(canonical_json(record_without_hash_field))
- 下一条记录的 hash_prev = 上一条 record_hash
- 维护一个 daily anchor：每天前 N 条记录 root 锚定 TSA（demo 不实做，留接口）
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

log = logging.getLogger("xa_guard.audit.merkle")

_HASH_PREV_KEY = "gen_ai.evidence.hash_prev"
_RECORD_HASH_KEY = "record_hash"
_SIGNATURE_KEY = "signature"
_LOCAL_LOCKS_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[str, threading.Lock] = {}


def _local_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.Lock())


@contextmanager
def _windows_named_mutex(path: Path, timeout_seconds: float) -> Iterator[None]:
    """Acquire a crash-safe Windows kernel mutex scoped to one audit path."""
    import ctypes
    from ctypes import wintypes

    mutex_key = os.path.normcase(str(path.resolve())).encode("utf-8")
    mutex_name = f"Local\\XA-Guard-Audit-{hashlib.sha256(mutex_key).hexdigest()}"
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.CreateMutexW(None, False, mutex_name)
    if not handle:
        raise OSError(ctypes.get_last_error(), f"cannot create audit mutex: {mutex_name}")
    acquired = False
    try:
        timeout_ms = min(max(round(timeout_seconds * 1000), 0), 0xFFFFFFFE)
        result = kernel32.WaitForSingleObject(handle, timeout_ms)
        if result in (0x00000000, 0x00000080):  # acquired or previous owner crashed
            acquired = True
        elif result == 0x00000102:
            raise TimeoutError(f"timed out waiting for audit lock: {path}")
        else:
            raise OSError(ctypes.get_last_error(), f"cannot wait for audit mutex: {mutex_name}")
        yield
    finally:
        if acquired:
            kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)


@contextmanager
def audit_file_lock(path: str | Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    """Cross-thread/process audit lock released automatically by the OS."""
    audit_path = Path(path)
    lock_path = audit_path.with_suffix(audit_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    local = _local_lock(lock_path)
    if not local.acquire(timeout=timeout_seconds):
        raise TimeoutError(f"timed out waiting for local audit lock: {lock_path}")
    handle = None
    locked = False
    try:
        if os.name == "nt":
            with _windows_named_mutex(lock_path, timeout_seconds):
                yield
            return

        handle = lock_path.open("a+b")
        deadline = time.monotonic() + timeout_seconds
        while not locked:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for audit lock: {lock_path}")
                time.sleep(0.01)
        yield
    finally:
        if handle is not None:
            if locked:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        local.release()


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def compute_record_hash(record_dict: dict[str, Any], algo: str = "sha256") -> str:
    """计算记录哈希（剔除自身 record_hash 和 signature 字段）。"""
    stripped = {k: v for k, v in record_dict.items() if k not in (_RECORD_HASH_KEY, _SIGNATURE_KEY)}
    data = canonical_json(stripped)
    if algo == "sm3":
        from xa_guard.audit.sm_crypto import sm3_hash

        return sm3_hash(data, prefer_gm=True)
    return hashlib.sha256(data).hexdigest()


class ChainStore:
    """JSONL 文件 + 内存维护最后哈希。

    启动时自动扫描已有文件最后一行恢复 _last_hash；append 追加；verify 全量校验。
    """

    def __init__(self, path: str | Path, algo: str = "sha256") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.algo = algo
        self._last_hash: str = ""
        self._known_file_state: tuple[int, int] | None = None
        self._recover_last_hash()

    def _file_state(self) -> tuple[int, int] | None:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return stat.st_size, stat.st_mtime_ns

    def _recover_last_hash(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            self._last_hash = ""
            self._known_file_state = self._file_state()
            return
        last = ""
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    last = line
            rec = json.loads(last)
            if not isinstance(rec, dict) or not rec.get(_RECORD_HASH_KEY):
                raise ValueError("last audit record has no record_hash")
            self._last_hash = str(rec[_RECORD_HASH_KEY])
            self._known_file_state = self._file_state()
        except Exception as exc:
            raise RuntimeError(f"cannot recover audit chain tail from {self.path}: {exc}") from exc

    @contextmanager
    def _append_lock(self, timeout_seconds: float = 10.0) -> Iterator[None]:
        with audit_file_lock(self.path, timeout_seconds=timeout_seconds):
            yield

    def append(
        self,
        record_dict: dict[str, Any],
        *,
        signer: Callable[[bytes], str] | None = None,
    ) -> dict[str, Any]:
        """Hash, optionally sign, and append one record under the writer lock."""
        with self._append_lock():
            # The lock protects cross-process writers. Re-scan only when another
            # writer or a signature patch changed the file since our last append.
            if self._file_state() != self._known_file_state:
                self._recover_last_hash()
            record_dict = dict(record_dict)  # 复制避免外部 mutate
            record_dict[_HASH_PREV_KEY] = self._last_hash
            # 不让外部预置 record_hash 干扰计算
            record_dict.pop(_RECORD_HASH_KEY, None)
            rec_hash = compute_record_hash(record_dict, self.algo)
            record_dict[_RECORD_HASH_KEY] = rec_hash
            if signer is not None:
                record_dict[_SIGNATURE_KEY] = signer(canonical_json(record_dict))

            line = canonical_json(record_dict).decode("utf-8")
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

            self._last_hash = rec_hash
            self._known_file_state = self._file_state()
            return record_dict

    def verify(self) -> tuple[bool, int | None]:
        """全量校验：逐行重算 record_hash 比对 + hash_prev 链对齐。
        返回 (ok, first_error_line_idx)；line_idx 从 1 起。
        """
        if not self.path.exists():
            return True, None
        prev_hash = ""
        with open(self.path, encoding="utf-8") as f:
            for idx, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    return False, idx

                actual_prev = rec.get(_HASH_PREV_KEY, "")
                if actual_prev != prev_hash:
                    return False, idx

                stored_hash = rec.get(_RECORD_HASH_KEY, "")
                recomputed = compute_record_hash(rec, self.algo)
                if stored_hash != recomputed:
                    return False, idx

                prev_hash = stored_hash
        return True, None

    @property
    def last_hash(self) -> str:
        return self._last_hash
