from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from enterprise_agent_range.arena.agent_seat import AgentSeat, RunTrace
from enterprise_agent_range.arena.challenge import Challenge
from enterprise_agent_range.arena.injection import build_world_for
from enterprise_agent_range.arena.oracle import Verdict, evaluate
from enterprise_agent_range.arena.sut import SUT
from enterprise_agent_range.io_utils import sha256_text, stable_json_dumps, utc_now_iso


@dataclass
class RunResult:
    challenge_id: str
    sut_id: str
    seat_id: str
    verdict: Verdict
    trace: RunTrace
    evidence: dict[str, Any]


def run_challenge(challenge: Challenge, seat: AgentSeat, sut: SUT, manifest_root: Path) -> RunResult:
    world = build_world_for(challenge, manifest_root)
    trace = seat.run(world, sut, challenge.task)
    verdict = evaluate(challenge, world, trace, sut)
    evidence = {
        "challenge_id": challenge.challenge_id,
        "kind": challenge.kind,
        "sut_id": sut.sut_id,
        "seat_id": seat.seat_id,
        "started_at": utc_now_iso(),
        "audit": [vars(a) for a in sut.audit],
        "egress": [vars(r) for r in world.egress],
        "verdict": vars(verdict),
        "trace_hash": sha256_text(stable_json_dumps([vars(step.call) for step in trace.steps])),
    }
    return RunResult(
        challenge_id=challenge.challenge_id,
        sut_id=sut.sut_id,
        seat_id=seat.seat_id,
        verdict=verdict,
        trace=trace,
        evidence=evidence,
    )
