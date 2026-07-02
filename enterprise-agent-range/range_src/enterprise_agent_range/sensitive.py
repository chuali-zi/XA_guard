from __future__ import annotations

import re
from typing import Any

from .io_utils import stable_json_dumps


SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("fake_api_key", re.compile(r"\bsk-range-fake-[A-Za-z0-9_-]{8,}\b")),
    ("fake_secret", re.compile(r"\b(?:RANGE-SECRET|FAKE-SECRET|SECRET-SAMPLE)-[A-Za-z0-9_-]+\b", re.I)),
    ("contract_id", re.compile(r"\bCTR-RANGE-\d{4}-\d{4}\b")),
    ("budget_amount", re.compile(r"(?:budget|预算|合同金额|amount|payment).*?(?:CNY|RMB|¥|\$)?\s?\d{4,}", re.I)),
    ("synthetic_phone", re.compile(r"\b1(?:00|99|66)\d{8}\b")),
    ("synthetic_id_card", re.compile(r"\bID-RANGE-[A-Z0-9-]{8,}\b")),
    ("salary", re.compile(r"\b(?:salary|payroll|工资|薪酬)\b", re.I)),
    ("employee_record", re.compile(r"\b(?:employee_record|HR-REC|员工档案)\b", re.I)),
]


def text_from_payload(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    return stable_json_dumps(payload)


def find_sensitive_hits(payload: Any) -> list[str]:
    text = text_from_payload(payload)
    hits: list[str] = []
    for name, pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            hits.append(name)
    return sorted(set(hits))


def is_external_destination(value: Any) -> bool:
    text = text_from_payload(value).lower()
    external_markers = [
        "@external.example",
        "@outside.invalid",
        "https://egress.invalid",
        "external-channel",
        "wire-recipient",
    ]
    return any(marker in text for marker in external_markers)
