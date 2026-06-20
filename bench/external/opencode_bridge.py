from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def invoke_opencode_json(
    prompt: str,
    *,
    executable: str,
    model: str,
    cwd: str | Path,
    config_home: str | Path,
    data_home: str | Path,
    timeout_seconds: float,
    invocation_log: str | Path | None = None,
    request_message: str = "Return the requested JSON object for the attached AgentDojo turn.",
) -> dict[str, Any]:
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(Path(config_home).resolve())
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
    }
    if invocation_log is not None:
        path = Path(invocation_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    if completed.returncode != 0:
        raise RuntimeError(
            f"OpenCode exited {completed.returncode}: {completed.stderr[-1000:]}"
        )
    if response is None:
        raise ValueError(parse_error or "OpenCode response parsing failed")
    return response
