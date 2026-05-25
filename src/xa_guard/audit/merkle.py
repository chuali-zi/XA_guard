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
from pathlib import Path
from typing import Any

log = logging.getLogger("xa_guard.audit.merkle")

_HASH_PREV_KEY = "gen_ai.evidence.hash_prev"
_RECORD_HASH_KEY = "record_hash"
_SIGNATURE_KEY = "signature"


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
        self._recover_last_hash()

    def _recover_last_hash(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        last = ""
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    last = line
            if last:
                rec = json.loads(last)
                self._last_hash = rec.get(_RECORD_HASH_KEY, "") or ""
        except Exception as exc:  # 损坏不影响启动
            log.warning("recover last hash failed: %s", exc)
            self._last_hash = ""

    def append(self, record_dict: dict[str, Any]) -> dict[str, Any]:
        """写 hash_prev → 计算 record_hash → JSONL 追加 → 更新 _last_hash。"""
        record_dict = dict(record_dict)  # 复制避免外部 mutate
        record_dict[_HASH_PREV_KEY] = self._last_hash
        # 不让外部预置 record_hash 干扰计算
        record_dict.pop(_RECORD_HASH_KEY, None)
        rec_hash = compute_record_hash(record_dict, self.algo)
        record_dict[_RECORD_HASH_KEY] = rec_hash

        line = canonical_json(record_dict).decode("utf-8")
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        self._last_hash = rec_hash
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
