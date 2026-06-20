from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentdojo.agent_pipeline.pi_detector import PromptInjectionDetector
from agentdojo.types import MessageContentBlock, text_content_block_from_string

from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.types import Decision, GateContext, InputSource

_MARKED_INSTRUCTION_BLOCKS = (
    re.compile(r"<information>.*?</information>", re.IGNORECASE | re.DOTALL),
    re.compile(r"\[system_instruction\].*?\[/system_instruction\]", re.IGNORECASE | re.DOTALL),
    re.compile(r"\[admin_override\].*?\[/admin_override\]", re.IGNORECASE | re.DOTALL),
)


def sanitize_detected_tool_output(text: str) -> tuple[str, bool]:
    sanitized = text
    for pattern in _MARKED_INSTRUCTION_BLOCKS:
        sanitized = pattern.sub("<untrusted_instruction omitted>", sanitized)
    if sanitized != text:
        return sanitized, True
    return "<Data omitted because XA-Guard detected a prompt injection>", False


class XAGuardPIDetector(PromptInjectionDetector):
    """AgentDojo pipeline element backed by XA-Guard Gate1.

    This element runs after official ``ToolsExecutor`` and before the next LLM
    turn. It therefore evaluates tool-result data rather than model output or
    benchmark labels. Official task execution and scorers remain unchanged.
    """

    name = "xa-guard-gate1"

    def __init__(self, *, decision_log: str | Path | None = None) -> None:
        super().__init__(mode="message", raise_on_injection=False)
        self.gate = Gate1Input()
        self.decision_log = Path(decision_log) if decision_log is not None else None
        self._last_detection: dict[str, Any] | None = None

    def detect(self, tool_output: str) -> tuple[bool, float]:
        result = self.gate.evaluate(
            GateContext(
                session_history=[{"role": "tool", "content": tool_output}],
                input_sources=[InputSource.TOOL_RESULT],
            )
        )
        blocked = result.decision in {Decision.DENY, Decision.REQUIRE_APPROVAL}
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "detection",
            "tool_output_sha256": hashlib.sha256(tool_output.encode("utf-8")).hexdigest(),
            "decision": result.decision.value,
            "blocked": blocked,
            "risks": result.risks,
            "detected_patterns": result.metadata.get("detected_patterns", []),
            "source": InputSource.TOOL_RESULT.value,
        }
        self._last_detection = record
        if self.decision_log is not None:
            self.decision_log.parent.mkdir(parents=True, exist_ok=True)
            with self.decision_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return blocked, 1.0 if blocked else 0.0

    def transform(
        self,
        tool_output: list[MessageContentBlock],
    ) -> list[MessageContentBlock]:
        transformed: list[MessageContentBlock] = []
        structured_redaction = False
        for block in tool_output:
            if block["type"] != "text":
                transformed.append(block)
                continue
            sanitized, preserved = sanitize_detected_tool_output(block["content"])
            structured_redaction = structured_redaction or preserved
            transformed.append(text_content_block_from_string(sanitized))
        if self._last_detection is not None and self.decision_log is not None:
            transform_record = {
                **self._last_detection,
                "event": "transformation",
                "structured_redaction": structured_redaction,
            }
            with self.decision_log.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(transform_record, ensure_ascii=False, sort_keys=True) + "\n"
                )
        return transformed
