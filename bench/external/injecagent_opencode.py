from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bench.external.opencode_bridge import invoke_opencode_json


@dataclass
class OpenCodeReActModel:
    """Neutral InjecAgent model adapter backed by OpenCode JSON mode."""

    executable: str
    model: str
    cwd: str | Path
    config_home: str | Path | None = None
    data_home: str | Path | None = None
    timeout_seconds: float = 180.0
    invocation_log: str | Path | None = None
    budget_ledger: str | Path | None = None
    budget_bucket: str | None = None
    budget_job_id: str | None = None
    max_invocation_reserve_usd: float | None = None

    def prepare_input(self, system_prompt: str, user_prompt: str) -> str:
        return (
            "Return exactly one JSON object with this schema:\n"
            '{"output":"the complete next ReAct response"}\n'
            "The output string must follow the benchmark format requested below. "
            "Do not add keys or commentary outside the JSON object.\n\n"
            "SYSTEM PROMPT:\n"
            f"{system_prompt}\n\n"
            "USER PROMPT:\n"
            f"{user_prompt}"
        )

    def call_model(self, model_input: str) -> str:
        response = invoke_opencode_json(
            model_input,
            executable=self.executable,
            model=self.model,
            cwd=self.cwd,
            config_home=self.config_home,
            data_home=self.data_home,
            timeout_seconds=self.timeout_seconds,
            invocation_log=self.invocation_log,
            budget_ledger=self.budget_ledger,
            budget_bucket=self.budget_bucket,
            budget_job_id=self.budget_job_id,
            max_invocation_reserve_usd=self.max_invocation_reserve_usd,
            request_message=(
                "Return the requested JSON object for the attached InjecAgent turn."
            ),
        )
        output = response.get("output")
        if not isinstance(output, str) or not output.strip():
            raise ValueError("OpenCode InjecAgent response must contain non-empty output")
        return output
