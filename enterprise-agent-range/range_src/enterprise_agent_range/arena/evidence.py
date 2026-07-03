from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Iterable

from enterprise_agent_range.io_utils import (
    append_jsonl,
    read_json,
    relative_to_root,
    sha256_file,
    write_json,
    write_jsonl,
)


@dataclass(frozen=True)
class AttemptPaths:
    """Stable evidence paths for one arena live attempt."""

    root: Path
    world_in: Path
    prompt: Path
    opencode_events: Path
    opencode_stderr: Path
    office_tool_events: Path
    world_effects: Path
    audit_dir: Path
    audit_events: Path
    audit_jsonl: Path
    verdict: Path
    artifact_hashes: Path
    opencode_config: Path
    opencode_live_agent: Path
    xa_guard_config: Path
    gate3_policy: Path
    gate4_capabilities: Path
    pending_approvals: Path

    @classmethod
    def for_attempt(cls, attempt_dir: Path) -> "AttemptPaths":
        root = attempt_dir
        audit_dir = root / "audit"
        return cls(
            root=root,
            world_in=root / "world-in.json",
            prompt=root / "prompt.txt",
            opencode_events=root / "opencode-events.jsonl",
            opencode_stderr=root / "opencode-stderr.txt",
            office_tool_events=root / "office-tool-events.jsonl",
            world_effects=root / "world-effects.jsonl",
            audit_dir=audit_dir,
            audit_events=audit_dir / "audit.jsonl",
            audit_jsonl=root / "audit.jsonl",
            verdict=root / "verdict.json",
            artifact_hashes=root / "artifact-hashes.json",
            opencode_config=root / "opencode.json",
            opencode_live_agent=root / "opencode-live-agent.txt",
            xa_guard_config=root / "xa-guard.yaml",
            gate3_policy=root / "gate3-rules.yaml",
            gate4_capabilities=root / "gate4-capabilities.yaml",
            pending_approvals=root / "pending_approvals.jsonl",
        )

    def evidence_files(self) -> list[Path]:
        """Return known evidence files, excluding directories and the hash manifest itself."""

        result: list[Path] = []
        for field in fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, Path):
                continue
            if value == self.root or value == self.audit_dir or value == self.artifact_hashes:
                continue
            result.append(value)
        return result


AttemptEvidence = AttemptPaths


class EvidenceStore:
    """Small stdlib-only store for arena attempt evidence artifacts."""

    def __init__(self, attempt_dir: Path | str) -> None:
        self.paths = AttemptPaths.for_attempt(Path(attempt_dir))
        self.paths.root.mkdir(parents=True, exist_ok=True)
        self.paths.audit_dir.mkdir(parents=True, exist_ok=True)

    @property
    def attempt_dir(self) -> Path:
        return self.paths.root

    def path(self, name: str) -> Path:
        try:
            value = getattr(self.paths, name)
        except AttributeError as exc:
            raise KeyError(f"unknown evidence path: {name}") from exc
        if not isinstance(value, Path):
            raise KeyError(f"evidence path is not a file path: {name}")
        return value

    def write_json(self, name: str, value: Any) -> Path:
        path = self.path(name)
        write_json(path, value)
        return path

    def read_json(self, name: str) -> dict[str, Any]:
        return read_json(self.path(name))

    def write_jsonl(self, name: str, rows: Iterable[dict[str, Any]]) -> Path:
        path = self.path(name)
        write_jsonl(path, list(rows))
        return path

    def append_jsonl(self, name: str, rows: Iterable[dict[str, Any]]) -> Path:
        path = self.path(name)
        append_jsonl(path, list(rows))
        return path

    def read_jsonl(self, name: str) -> list[dict[str, Any]]:
        path = self.path(name)
        if not path.exists():
            return []
        result: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    parsed = json.loads(stripped)
                    result.append(parsed if isinstance(parsed, dict) else {"value": parsed})
        return result

    def write_text(self, name: str, text: str) -> Path:
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def read_text(self, name: str) -> str:
        return self.path(name).read_text(encoding="utf-8")

    def finalize_artifact_hashes(self, extra_files: Iterable[Path] | None = None) -> dict[str, str]:
        files = [*self.paths.evidence_files()]
        if extra_files is not None:
            files.extend(Path(path) for path in extra_files)

        manifest: dict[str, str] = {}
        for path in files:
            if path == self.paths.artifact_hashes or not path.exists() or not path.is_file():
                continue
            manifest[relative_to_root(path, self.paths.root)] = sha256_file(path)

        write_json(self.paths.artifact_hashes, manifest)
        return manifest
