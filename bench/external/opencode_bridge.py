from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.external.budget import reserve_cost, settle_cost


class ProviderQuotaPaused(RuntimeError):
    """Provider rejected an unbilled call because a usage window is exhausted."""


def budget_bucket_for_attempt(
    attempt: int, primary_bucket: str | None, retry_bucket: str | None
) -> str | None:
    return primary_bucket if attempt <= 1 else retry_bucket or primary_bucket


def _is_provider_quota_error(stderr: str, stdout: str) -> bool:
    text = f"{stderr}\n{stdout}".lower()
    markers = (
        "quota exceeded",
        "quota exhausted",
        "usage limit",
        "weekly limit",
        "rate limit exceeded",
        "too many requests",
        "resource_exhausted",
    )
    return any(marker in text for marker in markers)


def parse_opencode_json_events(stdout: str) -> dict[str, Any]:
    text_parts: list[str] = []
    for line_no, raw_line in enumerate(stdout.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid OpenCode JSON event on line {line_no}") from exc
        if event.get("type") == "error":
            raise RuntimeError(f"OpenCode error event: {event.get('error')}")
        if event.get("type") == "text":
            value = event.get("part", {}).get("text")
            if isinstance(value, str):
                text_parts.append(value)
    if not text_parts:
        raise ValueError("OpenCode emitted no text event")

    text = text_parts[-1].strip()
    payload = None
    payload_span = -1
    decoder = json.JSONDecoder(strict=False)
    for offset, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[offset:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and end > payload_span:
            payload = value
            payload_span = end
    if payload is None:
        raise ValueError("OpenCode text event did not contain a JSON object")
    if not isinstance(payload, dict):
        raise ValueError("OpenCode response must be a JSON object")
    return payload


def parse_opencode_usage(stdout: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    token_totals = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0}
    costs: list[float] = []
    for raw_line in stdout.splitlines():
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "step_finish" or not isinstance(event.get("part"), dict):
            continue
        part = event["part"]
        cost = part.get("cost")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            costs.append(float(cost))
        tokens = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
        cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
        normalized = {
            "input": int(tokens.get("input", 0) or 0),
            "output": int(tokens.get("output", 0) or 0),
            "reasoning": int(tokens.get("reasoning", 0) or 0),
            "cache_read": int(cache.get("read", 0) or 0),
            "cache_write": int(cache.get("write", 0) or 0),
        }
        for key, value in normalized.items():
            token_totals[key] += value
        steps.append({"cost_usd": float(cost) if isinstance(cost, (int, float)) else None, "tokens": normalized})
    return {
        "step_count": len(steps),
        "cost_usd": sum(costs) if steps and len(costs) == len(steps) else None,
        "tokens": token_totals,
        "steps": steps,
    }


def invoke_opencode_json(
    prompt: str,
    *,
    executable: str,
    model: str,
    cwd: str | Path,
    config_home: str | Path | None = None,
    data_home: str | Path | None = None,
    timeout_seconds: float,
    invocation_log: str | Path | None = None,
    budget_ledger: str | Path | None = None,
    budget_bucket: str | None = None,
    budget_job_id: str | None = None,
    max_invocation_reserve_usd: float | None = None,
    request_message: str = "Return the requested JSON object for the attached AgentDojo turn.",
) -> dict[str, Any]:
    reservation_id = None
    if budget_ledger is not None:
        if budget_bucket is None or budget_job_id is None or max_invocation_reserve_usd is None:
            raise ValueError("budget ledger requires bucket, job id, and invocation reserve")
        reservation_id = reserve_cost(
            budget_ledger,
            bucket=budget_bucket,
            amount_usd=max_invocation_reserve_usd,
            job_id=budget_job_id,
        )
    env = os.environ.copy()
    # Only override XDG paths when explicitly provided.  Passing the real
    # user config dir on Windows can break provider-plugin discovery because
    # OpenCode's XDG resolution differs from the native %APPDATA% lookup.
    if config_home is not None:
        env["XDG_CONFIG_HOME"] = str(Path(config_home).resolve())
    if data_home is not None:
        env["XDG_DATA_HOME"] = str(Path(data_home).resolve())
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    runtime_cwd = Path(cwd).resolve()
    runtime_cwd.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".xa-agentdojo-turn-", dir=runtime_cwd
    ) as tmp_dir:
        prompt_path = Path(tmp_dir) / "turn.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        command = [
            executable,
            "run",
            request_message,
            "--pure",
            "--format",
            "json",
            "-m",
            model,
            "--file",
            str(prompt_path),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(runtime_cwd),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            completed = subprocess.CompletedProcess(
                command,
                124,
                stdout=stdout,
                stderr=f"{stderr}\nOpenCode timed out after {timeout_seconds} seconds".lstrip(),
            )
        except OSError as exc:
            completed = subprocess.CompletedProcess(
                command,
                125,
                stdout="",
                stderr=f"OpenCode process could not start: {exc}",
            )

        fallback_payloads: list[tuple[str, dict[str, Any]]] = []
        candidates = []
        for candidate in Path(tmp_dir).iterdir():
            if not candidate.is_file() or candidate == prompt_path:
                continue
            source = "temporary_json_file" if candidate.suffix == ".json" else "temporary_response_file"
            candidates.append((source, candidate))
        if prompt_path.read_text(encoding="utf-8") != prompt:
            candidates.append(("mutated_prompt_file", prompt_path))
        for source, candidate in candidates:
            try:
                value = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                fallback_payloads.append((source, value))

    try:
        if completed.returncode == 0:
            response = parse_opencode_json_events(completed.stdout)
            response_source = "text_event"
        else:
            response = None
            response_source = "none"
        parse_error = ""
    except (RuntimeError, ValueError) as exc:
        if fallback_payloads:
            response_source, response = fallback_payloads[-1]
        else:
            response_source, response = "none", None
        parse_error = "" if response is not None else str(exc)

    usage = parse_opencode_usage(completed.stdout)
    provider_quota_paused = (
        completed.returncode != 0
        and usage["step_count"] == 0
        and _is_provider_quota_error(completed.stderr, completed.stdout)
    )
    if provider_quota_paused:
        usage["cost_usd"] = 0.0
        usage["provider_quota_paused"] = True
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "prompt_sha256": prompt_sha256,
        "returncode": completed.returncode,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest(),
        "stderr": completed.stderr[-4000:],
        "parse_error": parse_error,
        "stdout_tail": completed.stdout[-8000:],
        "response_source": response_source,
        "response": response,
        "usage": usage,
        "error_kind": "provider_quota_paused" if provider_quota_paused else "",
    }
    if reservation_id is not None:
        settle_cost(
            budget_ledger,
            reservation_id=reservation_id,
            actual_cost_usd=usage["cost_usd"],
            usage=usage,
        )
    if invocation_log is not None:
        path = Path(invocation_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    if completed.returncode != 0:
        if provider_quota_paused:
            raise ProviderQuotaPaused(
                f"OpenCode provider quota paused: {completed.stderr[-1000:]}"
            )
        raise RuntimeError(
            f"OpenCode exited {completed.returncode}: {completed.stderr[-1000:]}"
        )
    if response is None:
        raise ValueError(parse_error or "OpenCode response parsing failed")
    return response
