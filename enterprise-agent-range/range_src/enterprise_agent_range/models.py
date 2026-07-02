from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CASE_KINDS = {
    "attack_case",
    "benign_control",
    "assurance_check",
    "exploratory_finding",
}

SURFACES = {
    "null_adapter",
    "sut_adapter",
    "mcp_stdio",
    "mcp_http",
    "simulated_ide",
    "manual",
}

RESULT_STATUSES = {
    "PASS",
    "FAIL",
    "INFRA_ERROR",
    "BLOCKED",
    "INVALID",
    "SKIPPED",
}

REQUIRED_CASE_FIELDS = {
    "case_id",
    "title",
    "case_kind",
    "taxonomy",
    "domain",
    "surface",
    "principal",
    "agent",
    "input",
    "expected",
    "safety",
    "evidence_requirements",
}

REQUIRED_AUDIT_FIELDS = {
    "trace_id",
    "case_id",
    "principal_id",
    "agent_id",
    "tool_name",
    "decision",
    "reason",
    "input_hash",
    "output_hash",
    "downstream_effect_hash",
    "timestamp",
    "sut_id",
    "environment_hash",
}


@dataclass(frozen=True)
class ManifestValidation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class LoadedManifest:
    path: Path
    root: Path
    data: dict[str, Any]
    validation: ManifestValidation

    @property
    def cases(self) -> list[dict[str, Any]]:
        return list(self.data.get("cases", []))

    @property
    def fixtures(self) -> list[dict[str, Any]]:
        return list(self.data.get("fixtures", []))

    @property
    def chains(self) -> list[dict[str, Any]]:
        return list(self.data.get("chains", []))


@dataclass
class ToolResult:
    tool_name: str
    output: dict[str, Any]
    side_effect_refs: list[str] = field(default_factory=list)


@dataclass
class CaseExecution:
    case: dict[str, Any]
    trace_id: str
    actual: dict[str, Any]
    tool_results: list[ToolResult]
    side_effects: list[dict[str, Any]]
    audit_records: list[dict[str, Any]]
    latency_ms: int
    infra_error: str | None = None


@dataclass(frozen=True)
class OracleOutcome:
    name: str
    passed: bool
    expected: Any
    actual: Any
    message: str = ""


@dataclass(frozen=True)
class CaseResult:
    run_id: str
    case_id: str
    trace_id: str
    case_kind: str
    taxonomy: list[str]
    domain: str
    surface: str
    expected: dict[str, Any]
    actual: dict[str, Any]
    status: str
    latency_ms: int
    oracle_results: list[OracleOutcome]
    evidence_refs: dict[str, str]
    infra_error: str | None = None

    def to_json(self) -> dict[str, Any]:
        row = {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "trace_id": self.trace_id,
            "case_kind": self.case_kind,
            "taxonomy": self.taxonomy,
            "domain": self.domain,
            "surface": self.surface,
            "expected": self.expected,
            "actual": self.actual,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "oracle_results": [
                {
                    "name": outcome.name,
                    "passed": outcome.passed,
                    "expected": outcome.expected,
                    "actual": outcome.actual,
                    "message": outcome.message,
                }
                for outcome in self.oracle_results
            ],
            "evidence_refs": self.evidence_refs,
        }
        if self.infra_error:
            row["infra_error"] = self.infra_error
        return row
