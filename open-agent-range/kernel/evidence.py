"""EvidenceStore — 每次 attempt 的证据包与 hash 清单。

契约见 ``docs/architecture/evidence-and-accountability.md`` §2。
移植自 arena ``evidence.py`` 的稳定布局，但去掉 office 专用字段、改为通用命名工件，
并内联 stdlib 实现（不依赖 arena io_utils），保持内核纯标准库。

证据必须可复算、可追责、可对照；目录命名建议 ``challenge_id/kind/sut_mode/attempt-NNN``。
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

# 每次 attempt 的稳定工件名（evidence-and-accountability.md §2 的通用化版本）。
ARTIFACT_NAMES = (
    "run-manifest.json",
    "world-in.json",
    "world-out.json",
    "world-diff.json",
    "prompt.txt",
    "transcript.jsonl",
    "agent-transcript.jsonl",
    "seat-events.jsonl",
    "tool-events.jsonl",
    "timeline.jsonl",
    "audit.jsonl",
    "sut-session.json",
    "world-effects.jsonl",
    "ledger.jsonl",
    "ledger-replay.json",
    "verdict.json",
    "accountability-report.json",
    # 生成的临时 SUT 配置（证据，非 XA-Guard 源码）：
    "gate3-rules.yaml",
    "gate4-capabilities.yaml",
    "xa-guard.yaml",
)
HASH_MANIFEST = "artifact-hashes.json"


class EvidenceStore:
    """stdlib-only 证据存储。写命名工件 + 收尾时产出 sha256 清单。"""

    def __init__(self, attempt_dir: Path | str) -> None:
        self.root = Path(attempt_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.root / name

    def write_json(self, name: str, value: Any) -> Path:
        path = self.path(name)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        return path

    def write_jsonl(self, name: str, rows: Iterable[dict[str, Any]]) -> Path:
        path = self.path(name)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.path(name)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def finalize_artifact_hashes(self) -> dict[str, str]:
        """对 attempt 目录下所有文件（除清单本身）算 sha256，写 artifact-hashes.json。"""
        manifest: dict[str, str] = {}
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.name == HASH_MANIFEST:
                continue
            digest = sha256(path.read_bytes()).hexdigest()
            manifest[path.relative_to(self.root).as_posix()] = digest
        self.write_json(HASH_MANIFEST, manifest)
        return manifest
