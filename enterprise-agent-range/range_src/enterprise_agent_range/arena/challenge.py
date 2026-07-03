from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Injection:
    into: str
    fixture: str


@dataclass(frozen=True)
class Task:
    principal: str
    agent: str
    prompt: str


@dataclass(frozen=True)
class OracleSpec:
    expected_decision: str
    data_exposure_absent: bool = True
    downstream_external_send_count: int = 0


@dataclass(frozen=True)
class PolicySpec:
    sensitive_markers: list[str] = field(default_factory=list)
    deny_external_tools: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Challenge:
    challenge_id: str
    world: str
    kind: str
    taxonomy: list[str]
    task: Task
    oracle: OracleSpec
    inject: list[Injection] = field(default_factory=list)
    policy: PolicySpec = field(default_factory=PolicySpec)


def challenge_from_dict(data: dict[str, Any]) -> Challenge:
    return Challenge(
        challenge_id=data["challenge_id"],
        world=data["world"],
        kind=data["kind"],
        taxonomy=list(data.get("taxonomy", [])),
        task=Task(**data["task"]),
        oracle=OracleSpec(**data["oracle"]),
        inject=[Injection(**item) for item in data.get("inject", [])],
        policy=PolicySpec(**data.get("policy", {})),
    )


def load_challenge(path: Path) -> Challenge:
    return challenge_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
