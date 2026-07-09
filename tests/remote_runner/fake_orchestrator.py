"""Scripted stand-in for scripts/run_r2_r3_acceptance.py used by supervisor tests.

Reads a JSON scenario (list of steps) from $XA_FAKE_SCENARIO. Each invocation
consumes the next step: prints its stdout, optionally writes fake job
state.json files under $XA_FAKE_OUTPUT_DIR, and exits with the given code.
The last step repeats once the list is exhausted. Every call's argv is
appended to <scenario>.calls.jsonl so tests can assert what the supervisor ran.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    scenario_path = Path(os.environ["XA_FAKE_SCENARIO"])
    steps = json.loads(scenario_path.read_text(encoding="utf-8"))
    counter_path = scenario_path.with_suffix(".counter")
    index = int(counter_path.read_text()) if counter_path.is_file() else 0
    counter_path.write_text(str(index + 1), encoding="utf-8")
    step = steps[min(index, len(steps) - 1)]

    with open(scenario_path.with_suffix(".calls.jsonl"), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(sys.argv[1:]) + "\n")

    output_dir = os.environ.get("XA_FAKE_OUTPUT_DIR")
    for job_id, state in step.get("write_states", {}).items():
        state_path = Path(output_dir) / "jobs" / job_id / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state), encoding="utf-8")

    if step.get("stdout"):
        print(step["stdout"])
    return int(step.get("exit", 0))


if __name__ == "__main__":
    raise SystemExit(main())
