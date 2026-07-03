from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from enterprise_agent_range.arena.injection import BOB, build_office_baseline
from enterprise_agent_range.arena.world import World

WorldFactory = Callable[[], World]


@dataclass(frozen=True)
class WorldSpec:
    world_id: str
    title: str
    description: str
    default_principal: str
    injection_targets: tuple[str, ...]
    factory: WorldFactory

    def build(self) -> World:
        return self.factory()


OFFICE_BASELINE = WorldSpec(
    world_id="office-baseline",
    title="Office mail baseline",
    description="Synthetic office mailbox and Atlas project budget world for red-team injection drills.",
    default_principal=BOB,
    injection_targets=(f"mailbox:{BOB}",),
    factory=build_office_baseline,
)

WORLD_SPECS: dict[str, WorldSpec] = {
    OFFICE_BASELINE.world_id: OFFICE_BASELINE,
}


def list_worlds() -> list[WorldSpec]:
    return [WORLD_SPECS[key] for key in sorted(WORLD_SPECS)]


def get_world_spec(world_id: str) -> WorldSpec:
    try:
        return WORLD_SPECS[world_id]
    except KeyError as exc:
        raise ValueError(f"unknown world: {world_id}") from exc


def build_world(world_id: str) -> World:
    return get_world_spec(world_id).build()