"""OpenTelemetry GenAI 适配。

demo：直接 JSON dict 写文件（避免引入 otel 全套依赖）。
M4 阶段：opentelemetry-sdk + langfuse exporter。

子 agent 实施：
- to_otel_dict(audit_record) -> dict（OTel GenAI Semantic Conventions key 风格）
"""
from __future__ import annotations

from xa_guard.types import AuditRecord


def to_otel_dict(record: AuditRecord) -> dict:
    """转换为 OTel GenAI Semantic Conventions 字典。"""
    return record.to_dict()
