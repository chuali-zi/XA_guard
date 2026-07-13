"""Local proposal engines for Auto-RedTeam.

The local engines are proposal-only: they ask a CLI agent to return one JSON
attack proposal, then the deterministic Conductor performs scope checks,
novelty checks, OAR execution, and verdict evaluation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class EngineError(RuntimeError):
    """Raised when a local CLI engine cannot produce a usable proposal."""


@dataclass(frozen=True)
class EngineResult:
    engine: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    proposal: dict[str, Any]


def available_executable(executable: str) -> str | None:
    """Return the resolved executable path, or None if it is not on PATH."""
    if Path(executable).is_file():
        return executable
    if os.name == "nt" and not Path(executable).suffix:
        for suffix in (".exe", ".cmd", ".bat", ".com"):
            resolved = shutil.which(executable + suffix)
            if resolved:
                return resolved
    return shutil.which(executable)


def _extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder(strict=False)
    best: dict[str, Any] | None = None
    best_span = -1
    for offset, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[offset:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and end > best_span:
            best = value
            best_span = end
    if best is None:
        raise EngineError("engine output did not contain a JSON object")
    return best


def _parse_jsonl_text_events(stdout: str) -> str:
    """Extract assistant text from common JSONL event streams."""
    parts: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "error":
            raise EngineError(f"engine emitted error event: {event.get('error')}")
        if event.get("type") == "text" and isinstance(event.get("part"), dict):
            value = event["part"].get("text")
            if isinstance(value, str):
                parts.append(value)
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            value = item.get("text")
            if isinstance(value, str):
                parts.append(value)
        message = event.get("message")
        if isinstance(message, dict):
            for item in message.get("content", []) or []:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
        result = event.get("result")
        if isinstance(result, str):
            parts.append(result)
        if isinstance(event.get("text"), str):
            parts.append(event["text"])
    return "\n".join(parts)


def parse_engine_output(stdout: str) -> dict[str, Any]:
    text = _parse_jsonl_text_events(stdout)
    if text.strip():
        return _extract_json_object(text)
    return _extract_json_object(stdout)


class LocalEngine:
    name = "local"

    def __init__(self, *, executable: str, model: str | None, timeout_s: int) -> None:
        self.executable = executable
        self.model = model
        self.timeout_s = timeout_s

    def available(self) -> bool:
        return available_executable(self.executable) is not None

    def build_command(self, mission_dir: Path, schema_path: Path | None = None) -> tuple[list[str], str | None, dict[str, str]]:
        raise NotImplementedError

    def propose(self, prompt: str, *, mission_dir: Path, schema_path: Path | None = None) -> EngineResult:
        resolved_executable = available_executable(self.executable)
        if not resolved_executable:
            raise EngineError(f"{self.name} executable not found: {self.executable}")
        prompt_path = mission_dir / "prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        command, stdin_text, env_updates = self.build_command(mission_dir, schema_path)
        command[0] = resolved_executable
        env = os.environ.copy()
        env.update(env_updates)
        try:
            completed = subprocess.run(
                command,
                input=prompt if stdin_text == "<stdin>" else stdin_text,
                cwd=str(mission_dir),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            raise EngineError(f"{self.name} timed out after {self.timeout_s}s: {stderr[-1000:]}") from exc
        except OSError as exc:
            raise EngineError(f"{self.name} could not start: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr[-1200:] or completed.stdout[-1200:]
            raise EngineError(f"{self.name} exited {completed.returncode}: {detail}")
        proposal = parse_engine_output(completed.stdout)
        return EngineResult(
            engine=self.name,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            proposal=proposal,
        )


class CursorCliEngine(LocalEngine):
    name = "cursor_cli"

    def build_command(self, mission_dir: Path, schema_path: Path | None = None) -> tuple[list[str], str | None, dict[str, str]]:
        cmd = [
            self.executable,
            "-p",
            "--mode",
            "ask",
            "--sandbox",
            "enabled",
            "--workspace",
            str(mission_dir),
            "--output-format",
            "stream-json",
            "--trust",
        ]
        if self.model:
            cmd.extend(["--model", self.model])
        cmd.append("Read prompt.md and return exactly one compact JSON attack proposal.")
        return cmd, None, {}


class OpenCodeEngine(LocalEngine):
    name = "opencode"

    def __init__(self, *, executable: str, model: str, variant: str, timeout_s: int) -> None:
        super().__init__(executable=executable, model=model, timeout_s=timeout_s)
        self.variant = variant

    def build_command(self, mission_dir: Path, schema_path: Path | None = None) -> tuple[list[str], str | None, dict[str, str]]:
        safe_config = {
            "$schema": "https://opencode.ai/config.json",
            "model": self.model,
            "permission": {
                "read": "allow",
                "list": "allow",
                "glob": "allow",
                "grep": "allow",
                "edit": "deny",
                "bash": "deny",
                "task": "deny",
                "webfetch": "deny",
                "websearch": "deny",
                "external_directory": "deny",
            },
        }
        env = {
            "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
            "OPENCODE_CONFIG_CONTENT": json.dumps(safe_config, ensure_ascii=False),
        }
        cmd = [
            self.executable,
            "run",
            "--pure",
            "--format",
            "json",
            "-m",
            str(self.model),
            "--variant",
            self.variant,
            "--file",
            str(mission_dir / "prompt.md"),
            "--dir",
            str(mission_dir),
            "Return exactly one compact JSON object matching prompt.md. No prose, markdown, tools, or code fences.",
        ]
        return cmd, None, env


class CodexEngine(LocalEngine):
    name = "codex"

    def __init__(self, *, executable: str, model: str, reasoning_effort: str, timeout_s: int) -> None:
        super().__init__(executable=executable, model=model, timeout_s=timeout_s)
        self.reasoning_effort = reasoning_effort

    def build_command(self, mission_dir: Path, schema_path: Path | None = None) -> tuple[list[str], str | None, dict[str, str]]:
        cmd = [
            self.executable,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "-m",
            str(self.model),
            "-c",
            f'model_reasoning_effort="{self.reasoning_effort}"',
            "-s",
            "read-only",
            "-C",
            str(mission_dir),
            "--json",
        ]
        cmd.append("-")
        return cmd, "<stdin>", {}


def build_engines(config: dict) -> list[LocalEngine]:
    names = [str(name) for name in config.get("engines", ["cursor_cli", "opencode", "codex"])]
    timeout_s = int(config.get("run_timeout_s", 1800))
    out: list[LocalEngine] = []
    for name in names:
        if name == "cursor_cli":
            out.append(
                CursorCliEngine(
                    executable=str(config.get("cursor_executable", "agent")),
                    model=config.get("cursor_model_id"),
                    timeout_s=timeout_s,
                )
            )
        elif name == "opencode":
            out.append(
                OpenCodeEngine(
                    executable=str(config.get("opencode_executable", "opencode")),
                    model=str(config.get("opencode_model_id", "openai/gpt-5.6-sol")),
                    variant=str(config.get("opencode_variant", "high")),
                    timeout_s=timeout_s,
                )
            )
        elif name == "codex":
            out.append(
                CodexEngine(
                    executable=str(config.get("codex_executable", "codex")),
                    model=str(config.get("codex_model_id", "gpt-5.6-sol")),
                    reasoning_effort=str(config.get("codex_reasoning_effort", "high")),
                    timeout_s=timeout_s,
                )
            )
        else:
            raise ValueError(f"unknown local engine: {name}")
    return out
