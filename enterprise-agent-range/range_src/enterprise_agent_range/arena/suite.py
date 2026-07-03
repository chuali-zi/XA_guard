from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ChallengeSuite:
    suite_id: str
    challenge_paths: tuple[Path, ...]

    def resolved_paths(self, root: Path) -> list[Path]:
        paths: list[Path] = []
        for path in self.challenge_paths:
            paths.append(path if path.is_absolute() else root / path)
        return paths


DEFAULT_ARENA_CHALLENGES: tuple[Path, ...] = (
    Path("cases/arena/OFFICE-INJ-001.attack.json"),
    Path("cases/arena/OFFICE-INJ-001.control.json"),
)


def default_suite() -> ChallengeSuite:
    return ChallengeSuite(suite_id="office-mail-smoke", challenge_paths=DEFAULT_ARENA_CHALLENGES)


def load_suite(path: Path) -> ChallengeSuite:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    suite_id = str(data.get("suite_id", Path(path).stem))
    raw_paths = data.get("challenge_paths", [])
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ValueError("suite must contain non-empty challenge_paths")
    return ChallengeSuite(suite_id=suite_id, challenge_paths=tuple(Path(str(item)) for item in raw_paths))


def suite_from_arg(path: Path | None) -> ChallengeSuite:
    return load_suite(path) if path is not None else default_suite()


def suite_to_json(suite: ChallengeSuite) -> dict[str, Any]:
    return {
        "suite_id": suite.suite_id,
        "challenge_paths": [path.as_posix() for path in suite.challenge_paths],
    }