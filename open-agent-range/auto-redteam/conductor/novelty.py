"""Deterministic novelty registry for proposal de-duplication."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NoveltyDecision:
    accepted: bool
    reason: str
    fingerprint: str
    max_similarity: float = 0.0


class NoveltyRegistry:
    def __init__(self, path: str | Path, *, similarity_threshold: float = 0.86) -> None:
        self.path = Path(path)
        self.similarity_threshold = similarity_threshold
        self.entries: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            self.entries = []
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.entries = list(data.get("entries", [])) if isinstance(data, dict) else []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "entries": self.entries}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def seed_from_injections(self, root: str | Path) -> None:
        root = Path(root)
        for path in sorted(root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            items = data.get("injections", []) if isinstance(data, dict) else data
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                pseudo = {
                    "objective_id": "prior-art",
                    "world": "prior-art",
                    "surface": str(item.get("into", "")).partition(":")[0],
                    "target": item.get("into", ""),
                    "expected_risk": "prior-art",
                    "technique_family": "seed-fixture",
                    "strategy_lane": "seed-fixture",
                    "payload": item.get("content", ""),
                }
                entry = self._entry(pseudo, engine="seed", verdict="PRIOR_ART")
                if not any(existing.get("fingerprint") == entry["fingerprint"] for existing in self.entries):
                    self.entries.append(entry)
        self.save()

    def decide(self, proposal: dict[str, Any]) -> NoveltyDecision:
        candidate = self._entry(proposal, engine="pending", verdict="PENDING")
        fingerprint = str(candidate["fingerprint"])
        for entry in self.entries:
            if entry.get("fingerprint") == fingerprint:
                return NoveltyDecision(False, "exact-duplicate", fingerprint, 1.0)
            if entry.get("successful_lane") and entry.get("structural_signature") == candidate.get("structural_signature"):
                return NoveltyDecision(False, "successful-strategy-lane-already-covered", fingerprint, 1.0)
        max_similarity = 0.0
        for entry in self.entries:
            similarity = _jaccard(_shingles(str(entry.get("normalized_payload", ""))), _shingles(str(candidate["normalized_payload"])))
            max_similarity = max(max_similarity, similarity)
            if similarity >= self.similarity_threshold:
                return NoveltyDecision(False, "payload-too-similar-to-prior-art", fingerprint, similarity)
        return NoveltyDecision(True, "accepted", fingerprint, max_similarity)

    def record(self, proposal: dict[str, Any], *, engine: str, verdict: str) -> str:
        entry = self._entry(proposal, engine=engine, verdict=verdict)
        entry["successful_lane"] = verdict in {"PASS", "BLOCKED"}
        self.entries.append(entry)
        self.save()
        return str(entry["fingerprint"])

    @staticmethod
    def _entry(proposal: dict[str, Any], *, engine: str, verdict: str) -> dict[str, Any]:
        normalized_payload = _normalize(str(proposal.get("payload", "")))
        structural = "|".join(
            str(proposal.get(key, ""))
            for key in ("world", "surface", "target", "expected_risk", "technique_family", "strategy_lane")
        )
        basis = json.dumps(
            {
                "structural": structural,
                "payload": normalized_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "fingerprint": hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24],
            "structural_signature": hashlib.sha256(structural.encode("utf-8")).hexdigest()[:24],
            "normalized_payload": normalized_payload,
            "objective_id": proposal.get("objective_id", ""),
            "surface": proposal.get("surface", ""),
            "world": proposal.get("world", ""),
            "target": proposal.get("target", ""),
            "technique_family": proposal.get("technique_family", ""),
            "strategy_lane": proposal.get("strategy_lane", ""),
            "engine": engine,
            "verdict": verdict,
        }


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", "", text)
    return text


def _shingles(text: str, width: int = 5) -> set[str]:
    if len(text) <= width:
        return {text} if text else set()
    return {text[i : i + width] for i in range(0, len(text) - width + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
