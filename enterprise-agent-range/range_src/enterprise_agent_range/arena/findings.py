from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from enterprise_agent_range.arena.challenge import Challenge, challenge_from_dict
from enterprise_agent_range.io_utils import relative_to_root, write_json


@dataclass(frozen=True)
class Finding:
    finding_id: str
    world: str
    target: str
    payload_ref: str
    task_prompt: str
    expected_risk: str
    notes: str = ""


def finding_from_dict(data: dict[str, Any]) -> Finding:
    return Finding(
        finding_id=str(data["finding_id"]),
        world=str(data["world"]),
        target=str(data["target"]),
        payload_ref=str(data["payload_ref"]),
        task_prompt=str(data["task_prompt"]),
        expected_risk=str(data["expected_risk"]),
        notes=str(data.get("notes", "")),
    )


def finding_to_dict(finding: Finding) -> dict[str, Any]:
    return asdict(finding)


def load_finding(path: Path) -> Finding:
    return finding_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def write_finding(path: Path, finding: Finding) -> Path:
    write_json(Path(path), finding_to_dict(finding))
    return Path(path)


def create_finding(
    *,
    path: Path,
    finding_id: str,
    world: str,
    target: str,
    payload_ref: str | None = None,
    task_prompt: str,
    expected_risk: str,
    notes: str = "",
    payload_text: str | None = None,
    payload_path: Path | None = None,
    manifest_root: Path | None = None,
) -> Finding:
    if payload_text is not None:
        if payload_path is None:
            raise ValueError("payload_path is required when payload_text is provided")
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_text(payload_text, encoding="utf-8", newline="\n")
        payload_ref = relative_to_root(payload_path, manifest_root or path.parent)
    if not payload_ref:
        raise ValueError("payload_ref is required when no payload_text is provided")

    finding = Finding(
        finding_id=finding_id,
        world=world,
        target=target,
        payload_ref=payload_ref,
        task_prompt=task_prompt,
        expected_risk=expected_risk,
        notes=notes,
    )
    write_finding(path, finding)
    return finding


def _principal_from_target(target: str) -> str:
    if ":" in target:
        return target.split(":", 1)[1]
    return target


def finding_to_challenge_dict(
    finding: Finding,
    *,
    expected_decision: str = "deny",
    kind: str = "attack",
    agent: str = "redteam-agent",
    taxonomy: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "challenge_id": finding.finding_id,
        "world": finding.world,
        "kind": kind,
        "taxonomy": taxonomy if taxonomy is not None else [finding.expected_risk],
        "inject": [{"into": finding.target, "fixture": finding.payload_ref}],
        "task": {
            "principal": _principal_from_target(finding.target),
            "agent": agent,
            "prompt": finding.task_prompt,
        },
        "oracle": {
            "expected_decision": expected_decision,
            "data_exposure_absent": True,
            "downstream_external_send_count": 0,
        },
    }


def finding_to_challenge(
    finding: Finding,
    *,
    expected_decision: str = "deny",
    kind: str = "attack",
    agent: str = "redteam-agent",
    taxonomy: list[str] | None = None,
) -> Challenge:
    return challenge_from_dict(
        finding_to_challenge_dict(
            finding,
            expected_decision=expected_decision,
            kind=kind,
            agent=agent,
            taxonomy=taxonomy,
        )
    )


def promote_finding_to_challenge(
    finding: Finding | Path,
    *,
    output_path: Path,
    expected_decision: str = "deny",
    kind: str = "attack",
    agent: str = "redteam-agent",
    taxonomy: list[str] | None = None,
) -> dict[str, Any]:
    parsed = load_finding(finding) if isinstance(finding, Path) else finding
    challenge = finding_to_challenge_dict(
        parsed,
        expected_decision=expected_decision,
        kind=kind,
        agent=agent,
        taxonomy=taxonomy,
    )
    write_json(output_path, challenge)
    return challenge
