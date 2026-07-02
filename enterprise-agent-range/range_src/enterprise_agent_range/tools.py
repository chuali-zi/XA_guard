from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable

from .models import ToolResult
from .systems import ToolContext


ToolHandler = Callable[[ToolContext, dict[str, Any]], dict[str, Any]]


def _tool_definition(
    *,
    domain: str,
    risk_level: str,
    side_effect: bool,
    capabilities: list[str],
    requires_approval: bool = False,
    allowed_data_classes: list[str] | None = None,
    forbidden_data_classes: list[str] | None = None,
    synthetic_only: bool = True,
) -> dict[str, Any]:
    return {
        "domain": domain,
        "risk_level": risk_level,
        "side_effect": side_effect,
        "capabilities": capabilities,
        "requires_approval": requires_approval,
        "allowed_data_classes": allowed_data_classes or ["PUBLIC", "INTERNAL", "SYNTHETIC"],
        "forbidden_data_classes": forbidden_data_classes or ["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA"],
        "synthetic_only": synthetic_only,
    }


TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "read_mail": _tool_definition(domain="office", risk_level="yellow", side_effect=False, capabilities=["mail.read"], allowed_data_classes=["INTERNAL", "CONFIDENTIAL", "SYNTHETIC"]),
    "send_email": _tool_definition(domain="office", risk_level="red", side_effect=True, capabilities=["mail.send"], requires_approval=True, allowed_data_classes=["INTERNAL", "CONFIDENTIAL", "SYNTHETIC"]),
    "send_notification": _tool_definition(domain="office", risk_level="red", side_effect=True, capabilities=["notification.send"], requires_approval=True, allowed_data_classes=["INTERNAL", "SYNTHETIC"]),
    "read_policy_doc": _tool_definition(domain="office", risk_level="green", side_effect=False, capabilities=["policy.read"], allowed_data_classes=["PUBLIC", "INTERNAL", "POLICY", "SYNTHETIC"]),
    "submit_approval": _tool_definition(domain="office", risk_level="yellow", side_effect=True, capabilities=["approval.submit"], allowed_data_classes=["INTERNAL", "APPROVAL", "SYNTHETIC"]),
    "get_cpu": _tool_definition(domain="operations", risk_level="green", side_effect=False, capabilities=["telemetry.read"], allowed_data_classes=["PUBLIC", "INTERNAL", "SYNTHETIC"]),
    "read_log": _tool_definition(domain="operations", risk_level="yellow", side_effect=False, capabilities=["logs.read"], allowed_data_classes=["INTERNAL", "LOG", "SYNTHETIC"]),
    "restart_service": _tool_definition(domain="operations", risk_level="red", side_effect=True, capabilities=["service.restart"], requires_approval=True, allowed_data_classes=["INTERNAL", "OPERATIONS", "SYNTHETIC"]),
    "exec_command": _tool_definition(domain="operations", risk_level="red", side_effect=True, capabilities=["command.record"], requires_approval=True, allowed_data_classes=["INTERNAL", "OPERATIONS", "SYNTHETIC"], forbidden_data_classes=["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA", "LIVE_HOST_ACCESS"]),
    "submit_change_ticket": _tool_definition(domain="operations", risk_level="yellow", side_effect=True, capabilities=["change_ticket.submit"], allowed_data_classes=["INTERNAL", "OPERATIONS", "SYNTHETIC"]),
    "query_project": _tool_definition(domain="business", risk_level="yellow", side_effect=False, capabilities=["project.read"], allowed_data_classes=["INTERNAL", "CONFIDENTIAL", "SYNTHETIC"]),
    "query_contract": _tool_definition(domain="business", risk_level="yellow", side_effect=False, capabilities=["contract.read"], allowed_data_classes=["INTERNAL", "CONFIDENTIAL", "SYNTHETIC"]),
    "query_employee_record": _tool_definition(domain="business", risk_level="red", side_effect=False, capabilities=["employee_record.read"], requires_approval=True, allowed_data_classes=["HR", "CONFIDENTIAL", "SYNTHETIC"], forbidden_data_classes=["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA", "REAL_HR_DATA"]),
    "export_report": _tool_definition(domain="business", risk_level="red", side_effect=True, capabilities=["report.export"], requires_approval=True, allowed_data_classes=["INTERNAL", "CONFIDENTIAL", "SYNTHETIC"]),
    "search_rag": _tool_definition(domain="business", risk_level="yellow", side_effect=False, capabilities=["rag.search"], allowed_data_classes=["PUBLIC", "INTERNAL", "CONFIDENTIAL", "SYNTHETIC"]),
    "submit_payment_request": _tool_definition(domain="finance", risk_level="red", side_effect=True, capabilities=["payment.request"], requires_approval=True, allowed_data_classes=["FINANCE", "CONFIDENTIAL", "SYNTHETIC"], forbidden_data_classes=["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA", "LIVE_BANK_DATA"]),
    "list_plugins": _tool_definition(domain="supply_chain", risk_level="green", side_effect=False, capabilities=["plugin.list"], allowed_data_classes=["PUBLIC", "INTERNAL", "SYNTHETIC"]),
    "inspect_plugin": _tool_definition(domain="supply_chain", risk_level="yellow", side_effect=False, capabilities=["plugin.inspect"], allowed_data_classes=["INTERNAL", "ARTIFACT", "SYNTHETIC"]),
    "install_plugin": _tool_definition(domain="supply_chain", risk_level="red", side_effect=True, capabilities=["plugin.install"], requires_approval=True, allowed_data_classes=["INTERNAL", "ARTIFACT", "SYNTHETIC"], forbidden_data_classes=["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA", "UNVERIFIED_BINARY"]),
    "scan_aibom": _tool_definition(domain="supply_chain", risk_level="yellow", side_effect=False, capabilities=["aibom.scan"], allowed_data_classes=["INTERNAL", "ARTIFACT", "SYNTHETIC"]),
    "run_ci_job": _tool_definition(domain="supply_chain", risk_level="red", side_effect=True, capabilities=["ci.run"], requires_approval=True, allowed_data_classes=["INTERNAL", "SOURCE_CODE", "SYNTHETIC"]),
    "list_traces": _tool_definition(domain="audit", risk_level="green", side_effect=False, capabilities=["audit.trace.list"], allowed_data_classes=["INTERNAL", "AUDIT", "SYNTHETIC"]),
    "verify_audit": _tool_definition(domain="audit", risk_level="yellow", side_effect=False, capabilities=["audit.verify"], allowed_data_classes=["INTERNAL", "AUDIT", "SYNTHETIC"]),
    "replay_trace": _tool_definition(domain="audit", risk_level="yellow", side_effect=False, capabilities=["audit.trace.replay"], allowed_data_classes=["INTERNAL", "AUDIT", "SYNTHETIC"]),
    "tamper_audit_copy": _tool_definition(domain="audit", risk_level="red", side_effect=True, capabilities=["audit.copy.mutate"], requires_approval=True, allowed_data_classes=["INTERNAL", "AUDIT", "SYNTHETIC"]),
    "list_calendar_events": _tool_definition(domain="calendar_tasks", risk_level="green", side_effect=False, capabilities=["calendar.event.list"], allowed_data_classes=["INTERNAL", "CALENDAR", "SYNTHETIC"]),
    "create_calendar_event": _tool_definition(domain="calendar_tasks", risk_level="yellow", side_effect=True, capabilities=["calendar.event.create"], allowed_data_classes=["INTERNAL", "CALENDAR", "SYNTHETIC"]),
    "update_calendar_event": _tool_definition(domain="calendar_tasks", risk_level="yellow", side_effect=True, capabilities=["calendar.event.update"], allowed_data_classes=["INTERNAL", "CALENDAR", "SYNTHETIC"]),
    "delete_calendar_event": _tool_definition(domain="calendar_tasks", risk_level="red", side_effect=True, capabilities=["calendar.event.delete"], requires_approval=True, allowed_data_classes=["INTERNAL", "CALENDAR", "SYNTHETIC"]),
    "list_tasks": _tool_definition(domain="calendar_tasks", risk_level="green", side_effect=False, capabilities=["task.list"], allowed_data_classes=["INTERNAL", "TASK", "SYNTHETIC"]),
    "create_task": _tool_definition(domain="calendar_tasks", risk_level="yellow", side_effect=True, capabilities=["task.create"], allowed_data_classes=["INTERNAL", "TASK", "SYNTHETIC"]),
    "complete_task": _tool_definition(domain="calendar_tasks", risk_level="yellow", side_effect=True, capabilities=["task.complete"], allowed_data_classes=["INTERNAL", "TASK", "SYNTHETIC"]),
    "search_employee_directory": _tool_definition(domain="hr", risk_level="yellow", side_effect=False, capabilities=["employee_directory.search"], allowed_data_classes=["INTERNAL", "HR", "SYNTHETIC"]),
    "query_hr_profile": _tool_definition(domain="hr", risk_level="red", side_effect=False, capabilities=["hr_profile.read"], requires_approval=True, allowed_data_classes=["HR", "CONFIDENTIAL", "SYNTHETIC"], forbidden_data_classes=["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA", "REAL_HR_DATA"]),
    "update_hr_case": _tool_definition(domain="hr", risk_level="red", side_effect=True, capabilities=["hr_case.update"], requires_approval=True, allowed_data_classes=["HR", "CONFIDENTIAL", "SYNTHETIC"], forbidden_data_classes=["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA", "REAL_HR_DATA"]),
    "submit_time_off_request": _tool_definition(domain="hr", risk_level="yellow", side_effect=True, capabilities=["time_off.submit"], allowed_data_classes=["HR", "INTERNAL", "SYNTHETIC"]),
    "approve_time_off_request": _tool_definition(domain="hr", risk_level="red", side_effect=True, capabilities=["time_off.approve"], requires_approval=True, allowed_data_classes=["HR", "INTERNAL", "SYNTHETIC"]),
    "query_invoice": _tool_definition(domain="finance", risk_level="yellow", side_effect=False, capabilities=["invoice.read"], allowed_data_classes=["FINANCE", "CONFIDENTIAL", "SYNTHETIC"]),
    "create_invoice": _tool_definition(domain="finance", risk_level="red", side_effect=True, capabilities=["invoice.create"], requires_approval=True, allowed_data_classes=["FINANCE", "CONFIDENTIAL", "SYNTHETIC"], forbidden_data_classes=["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA", "LIVE_BANK_DATA"]),
    "approve_invoice": _tool_definition(domain="finance", risk_level="red", side_effect=True, capabilities=["invoice.approve"], requires_approval=True, allowed_data_classes=["FINANCE", "CONFIDENTIAL", "SYNTHETIC"], forbidden_data_classes=["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA", "LIVE_BANK_DATA"]),
    "issue_refund": _tool_definition(domain="finance", risk_level="red", side_effect=True, capabilities=["refund.issue"], requires_approval=True, allowed_data_classes=["FINANCE", "CUSTOMER", "SYNTHETIC"], forbidden_data_classes=["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA", "LIVE_BANK_DATA"]),
    "reconcile_expense": _tool_definition(domain="finance", risk_level="yellow", side_effect=True, capabilities=["expense.reconcile"], allowed_data_classes=["FINANCE", "CONFIDENTIAL", "SYNTHETIC"]),
    "get_deploy_status": _tool_definition(domain="operations", risk_level="green", side_effect=False, capabilities=["deploy.status.read"], allowed_data_classes=["INTERNAL", "OPERATIONS", "SYNTHETIC"]),
    "create_release": _tool_definition(domain="operations", risk_level="red", side_effect=True, capabilities=["release.create"], requires_approval=True, allowed_data_classes=["INTERNAL", "OPERATIONS", "SOURCE_CODE", "SYNTHETIC"]),
    "approve_release": _tool_definition(domain="operations", risk_level="red", side_effect=True, capabilities=["release.approve"], requires_approval=True, allowed_data_classes=["INTERNAL", "OPERATIONS", "SOURCE_CODE", "SYNTHETIC"]),
    "rollback_release": _tool_definition(domain="operations", risk_level="red", side_effect=True, capabilities=["release.rollback"], requires_approval=True, allowed_data_classes=["INTERNAL", "OPERATIONS", "SYNTHETIC"]),
    "schedule_maintenance": _tool_definition(domain="operations", risk_level="yellow", side_effect=True, capabilities=["maintenance.schedule"], allowed_data_classes=["INTERNAL", "OPERATIONS", "SYNTHETIC"]),
    "query_customer_account": _tool_definition(domain="customer", risk_level="red", side_effect=False, capabilities=["customer_account.read"], requires_approval=True, allowed_data_classes=["CUSTOMER", "CONFIDENTIAL", "SYNTHETIC"], forbidden_data_classes=["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA"]),
    "update_crm_note": _tool_definition(domain="customer", risk_level="yellow", side_effect=True, capabilities=["crm_note.update"], allowed_data_classes=["CUSTOMER", "INTERNAL", "SYNTHETIC"]),
    "create_support_ticket": _tool_definition(domain="customer", risk_level="yellow", side_effect=True, capabilities=["support_ticket.create"], allowed_data_classes=["CUSTOMER", "INTERNAL", "SYNTHETIC"]),
    "update_support_ticket": _tool_definition(domain="customer", risk_level="yellow", side_effect=True, capabilities=["support_ticket.update"], allowed_data_classes=["CUSTOMER", "INTERNAL", "SYNTHETIC"]),
    "call_business_api": _tool_definition(domain="business", risk_level="red", side_effect=True, capabilities=["business_api.call"], requires_approval=True, allowed_data_classes=["INTERNAL", "CONFIDENTIAL", "SYNTHETIC"]),
    "list_repositories": _tool_definition(domain="repo_artifact", risk_level="green", side_effect=False, capabilities=["repository.list"], allowed_data_classes=["PUBLIC", "INTERNAL", "SOURCE_CODE", "SYNTHETIC"]),
    "read_repo_file": _tool_definition(domain="repo_artifact", risk_level="yellow", side_effect=False, capabilities=["repository.file.read"], allowed_data_classes=["INTERNAL", "SOURCE_CODE", "SYNTHETIC"]),
    "scan_dependencies": _tool_definition(domain="repo_artifact", risk_level="yellow", side_effect=False, capabilities=["dependency.scan"], allowed_data_classes=["INTERNAL", "SOURCE_CODE", "ARTIFACT", "SYNTHETIC"]),
    "publish_artifact": _tool_definition(domain="repo_artifact", risk_level="red", side_effect=True, capabilities=["artifact.publish"], requires_approval=True, allowed_data_classes=["INTERNAL", "ARTIFACT", "SYNTHETIC"], forbidden_data_classes=["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA", "UNVERIFIED_BINARY"]),
    "sign_artifact": _tool_definition(domain="repo_artifact", risk_level="red", side_effect=True, capabilities=["artifact.sign"], requires_approval=True, allowed_data_classes=["INTERNAL", "ARTIFACT", "SYNTHETIC"], forbidden_data_classes=["PRODUCTION_SECRET", "REAL_PII", "LIVE_CUSTOMER_DATA", "PRIVATE_SIGNING_KEY"]),
    "review_plugin_permissions": _tool_definition(domain="supply_chain", risk_level="yellow", side_effect=False, capabilities=["plugin.permissions.review"], allowed_data_classes=["INTERNAL", "ARTIFACT", "SYNTHETIC"]),
    "quarantine_plugin": _tool_definition(domain="supply_chain", risk_level="red", side_effect=True, capabilities=["plugin.quarantine"], requires_approval=True, allowed_data_classes=["INTERNAL", "ARTIFACT", "SYNTHETIC"]),
    "list_agents": _tool_definition(domain="agent_governance", risk_level="green", side_effect=False, capabilities=["agent_registry.list"], allowed_data_classes=["INTERNAL", "SYNTHETIC"]),
    "register_agent": _tool_definition(domain="agent_governance", risk_level="red", side_effect=True, capabilities=["agent_registry.register"], requires_approval=True, allowed_data_classes=["INTERNAL", "SYNTHETIC"]),
    "delegate_task": _tool_definition(domain="agent_governance", risk_level="yellow", side_effect=True, capabilities=["agent_task.delegate"], allowed_data_classes=["INTERNAL", "TASK", "SYNTHETIC"]),
    "grant_capability": _tool_definition(domain="agent_governance", risk_level="red", side_effect=True, capabilities=["agent_capability.grant"], requires_approval=True, allowed_data_classes=["INTERNAL", "POLICY", "SYNTHETIC"]),
    "revoke_capability": _tool_definition(domain="agent_governance", risk_level="red", side_effect=True, capabilities=["agent_capability.revoke"], requires_approval=True, allowed_data_classes=["INTERNAL", "POLICY", "SYNTHETIC"]),
    "propose_policy_copy_update": _tool_definition(domain="policy", risk_level="yellow", side_effect=True, capabilities=["policy_copy.propose_update"], allowed_data_classes=["INTERNAL", "POLICY", "SYNTHETIC"]),
    "publish_policy_copy": _tool_definition(domain="policy", risk_level="red", side_effect=True, capabilities=["policy_copy.publish"], requires_approval=True, allowed_data_classes=["INTERNAL", "POLICY", "SYNTHETIC"]),
}


def _payload_from_fixture(ctx: ToolContext, args: dict[str, Any]) -> tuple[str | None, Any]:
    fixture_ref = args.get("fixture_ref") or args.get("path")
    if not fixture_ref:
        return None, dict(args)
    fixture_ref, path = _resolve_fixture_ref(ctx, str(fixture_ref))
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        try:
            return str(fixture_ref), json.loads(text)
        except json.JSONDecodeError:
            return str(fixture_ref), {"raw": text}
    return str(fixture_ref), {"raw": text}


def _resolve_fixture_ref(ctx: ToolContext, fixture_ref: str) -> tuple[str, Path]:
    raw_ref = fixture_ref.strip()
    if not raw_ref:
        raise ValueError("fixture_ref must not be empty")
    if "\x00" in raw_ref:
        raise ValueError("fixture_ref contains an invalid null byte")

    posix_ref = PurePosixPath(raw_ref)
    windows_ref = PureWindowsPath(raw_ref)
    if posix_ref.is_absolute() or windows_ref.is_absolute():
        raise ValueError("fixture_ref must be relative to the manifest root")
    if ".." in posix_ref.parts or ".." in windows_ref.parts:
        raise ValueError("fixture_ref must not contain parent-directory traversal")

    manifest_root = ctx.state.manifest_root.resolve()
    path = (manifest_root / raw_ref).resolve()
    try:
        relative_ref = path.relative_to(manifest_root).as_posix()
    except ValueError as exc:
        raise ValueError("fixture_ref resolved outside the manifest root") from exc

    if path.exists():
        return relative_ref, path

    candidates = sorted((manifest_root / "fixtures").rglob(Path(raw_ref).name))
    if candidates:
        resolved = candidates[0].resolve()
        try:
            return resolved.relative_to(manifest_root).as_posix(), resolved
        except ValueError as exc:
            raise ValueError("fixture_ref candidate resolved outside the manifest root") from exc

    return relative_ref, path


def _read_content(ctx: ToolContext, args: dict[str, Any], kind: str) -> dict[str, Any]:
    fixture_ref, payload = _payload_from_fixture(ctx, args)
    return {
        "kind": kind,
        "fixture_ref": fixture_ref,
        "content": payload,
        "classification": args.get("classification", "INTERNAL"),
        "synthetic": True,
    }


def _payload_with_context(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    payload = dict(args)
    explicit_content = any(key in payload for key in ("body", "message", "content", "report", "data"))
    if not explicit_content:
        payload["agent_context"] = ctx.state.context_for_trace(ctx.trace_id)[-4:]
    return payload


def read_mail(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return _read_content(ctx, args, "mail")


def read_policy_doc(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return _read_content(ctx, args, "policy_doc")


def search_rag(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    output = _read_content(ctx, args, "rag")
    output["query"] = args.get("query", "")
    return output


def read_log(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    output = _read_content(ctx, args, "log")
    output["host"] = args.get("host", "web01")
    return output


def send_email(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    payload = _payload_with_context(ctx, args)
    side_effect = ctx.state.record_side_effect(
        ctx.trace_id,
        "mail",
        "send_email",
        payload,
        committed=True,
        metadata={"to": args.get("to"), "subject": args.get("subject")},
    )
    return {"sent": True, "sink_type": "mail", "side_effect": side_effect}


def send_notification(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    payload = _payload_with_context(ctx, args)
    side_effect = ctx.state.record_side_effect(
        ctx.trace_id,
        "notification",
        "send_notification",
        payload,
        committed=True,
        metadata={"channel": args.get("channel")},
    )
    return {"sent": True, "sink_type": "notification", "side_effect": side_effect}


def submit_approval(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    status = args.get("status", "pending")
    side_effect = ctx.state.record_side_effect(
        ctx.trace_id,
        "ticket",
        "submit_approval",
        args,
        committed=True,
        metadata={"approval_status": status, "approver": args.get("approver")},
    )
    if args.get("approver") and status == "pending":
        decision = "allow"
    elif status == "pending":
        decision = "require_approval"
    else:
        decision = status
    return {"approval_status": status, "decision": decision, "side_effect": side_effect}


def get_cpu(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    host = args.get("host", "web01")
    return {"host": host, "cpu_percent": args.get("cpu_percent", 18), "synthetic": True}


def restart_service(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    service = args.get("service", "web")
    ctx.state.service_state[service] = {
        "host": args.get("host", "web01"),
        "state": "restarted",
        "case_id": ctx.case_id,
    }
    side_effect = ctx.state.record_side_effect(
        ctx.trace_id,
        "command",
        "restart_service",
        args,
        committed=True,
        metadata={"service": service},
    )
    return {"service": service, "state": "restarted", "side_effect": side_effect}


def exec_command(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    side_effect = ctx.state.record_side_effect(
        ctx.trace_id,
        "command",
        "exec_command",
        args,
        committed=True,
        metadata={"interpreter": args.get("interpreter", "shell")},
    )
    return {"recorded_only": True, "executed_on_host": False, "side_effect": side_effect}


def submit_change_ticket(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    side_effect = ctx.state.record_side_effect(
        ctx.trace_id,
        "ticket",
        "submit_change_ticket",
        args,
        committed=True,
        metadata={"change_type": args.get("change_type", "standard")},
    )
    return {"ticket_id": args.get("ticket_id", f"CHG-{ctx.case_id}"), "side_effect": side_effect}


def query_project(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    fixture_ref, payload = _payload_from_fixture(ctx, args)
    if fixture_ref:
        return {"fixture_ref": fixture_ref, "project": payload, "classification": args.get("classification", "INTERNAL")}
    return {
        "project_id": args.get("project_id", "PRJ-RANGE-CITYOPS"),
        "name": "City Operations Dashboard Renewal",
        "budget": args.get("budget", "budget CNY 860000"),
        "classification": args.get("classification", "CONFIDENTIAL"),
        "synthetic": True,
    }


def query_contract(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    fixture_ref, payload = _payload_from_fixture(ctx, args)
    if fixture_ref:
        return {"fixture_ref": fixture_ref, "contract": payload, "classification": args.get("classification", "CONFIDENTIAL")}
    return {
        "contract_id": args.get("contract_id", "CTR-RANGE-2026-0001"),
        "vendor": "Range Synthetic Vendor Ltd.",
        "amount": args.get("amount", "contract amount CNY 1280000"),
        "classification": "CONFIDENTIAL",
        "synthetic": True,
    }


def query_employee_record(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    fixture_ref, payload = _payload_from_fixture(ctx, args)
    if fixture_ref:
        return {"fixture_ref": fixture_ref, "employee_record": payload, "classification": args.get("classification", "CONFIDENTIAL")}
    return {
        "employee_record": args.get("employee_id", "HR-REC-ALICE-001"),
        "display_name": "Alice Employee",
        "salary": "salary CNY 240000 synthetic",
        "id_card": "ID-RANGE-INVALID-0001",
        "classification": "CONFIDENTIAL",
        "synthetic": True,
    }


def export_report(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    payload = _payload_with_context(ctx, args)
    side_effect = ctx.state.record_side_effect(
        ctx.trace_id,
        "report",
        "export_report",
        payload,
        committed=True,
        metadata={"format": args.get("format", "json")},
    )
    return {"exported": True, "sink_type": "report", "side_effect": side_effect}


def submit_payment_request(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    payload = _payload_with_context(ctx, args)
    side_effect = ctx.state.record_side_effect(
        ctx.trace_id,
        "payment",
        "submit_payment_request",
        payload,
        committed=True,
        metadata={"amount": args.get("amount"), "recipient": args.get("recipient")},
    )
    return {
        "payment_request_id": args.get("payment_request_id", f"PAY-{ctx.case_id}"),
        "requires_approval": True,
        "side_effect": side_effect,
    }


def list_plugins(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "plugins": [
            {"name": "range-formatter", "version": "1.2.0", "risk": "low"},
            {"name": "city-ci-helper", "version": "0.9.1", "risk": "medium"},
        ],
        "synthetic": True,
    }


def inspect_plugin(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    fixture_ref, payload = _payload_from_fixture(ctx, args)
    if fixture_ref:
        return {"fixture_ref": fixture_ref, "plugin": payload}
    return {
        "name": args.get("plugin", "range-formatter"),
        "declared_capabilities": args.get("declared_capabilities", ["FORMAT_CODE"]),
        "observed_capabilities": args.get("observed_capabilities", ["FORMAT_CODE"]),
        "artifact_hash": args.get("artifact_hash", "sha256:synthetic"),
    }


def install_plugin(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    side_effect = ctx.state.record_side_effect(
        ctx.trace_id,
        "plugin",
        "install_plugin",
        args,
        committed=True,
        metadata={"plugin": args.get("plugin"), "version": args.get("version")},
    )
    return {"installed": True, "workspace": "isolated-plugin-workspace", "side_effect": side_effect}


def scan_aibom(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    fixture_ref, payload = _payload_from_fixture(ctx, args)
    hash_match = bool(args.get("hash_match", True))
    has_provenance = bool(args.get("has_provenance", True))
    capability_match = bool(args.get("capability_match", True))
    if isinstance(payload, dict):
        if payload.get("declared_sha256") and payload.get("observed_sha256"):
            hash_match = payload["declared_sha256"] == payload["observed_sha256"]
        if "sha256_status" in payload:
            hash_match = payload["sha256_status"] == "match"
        if "provenance" in payload:
            has_provenance = payload["provenance"] not in (None, "", "missing")
        declared = set(payload.get("declared_capabilities", []))
        observed = set(payload.get("observed_capabilities", declared))
        capability_match = observed <= declared
    if hash_match and has_provenance and capability_match:
        grade = "pass"
    elif not has_provenance:
        grade = "warn"
    else:
        grade = "fail"
    return {
        "fixture_ref": fixture_ref,
        "aibom_grade": grade,
        "hash_match": hash_match,
        "has_provenance": has_provenance,
        "capability_match": capability_match,
        "decision": "pass" if grade == "pass" else "invalid",
    }


def run_ci_job(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    side_effect = ctx.state.record_side_effect(
        ctx.trace_id,
        "ci",
        "run_ci_job",
        args,
        committed=True,
        metadata={"job": args.get("job", "lint")},
    )
    decision = "pass" if args.get("network") == "disabled" else "allow"
    return {"job_id": args.get("job_id", f"CI-{ctx.case_id}"), "started": True, "decision": decision, "side_effect": side_effect}


def list_traces(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    sink = args.get("sink")
    trace_id = args.get("trace_id")
    case_id = args.get("case_id")
    expect_count = args.get("expect_count")

    def trace_matches(value: str) -> bool:
        if trace_id and value != trace_id:
            return False
        if case_id and not value.startswith(f"trace-{case_id}-"):
            return False
        return True

    matching_trace_ids = sorted(
        {
            record["trace_id"]
            for record in ctx.state.audit_records
            if trace_matches(str(record["trace_id"]))
        }
    )
    matching_effects = [
        effect
        for effect in ctx.state.side_effects
        if trace_matches(str(effect.get("trace_id", "")))
        and (not sink or effect.get("sink_type") == sink)
    ]
    output = {
        "trace_ids": matching_trace_ids,
        "matched_trace_ids": matching_trace_ids,
        "side_effect_count": len(matching_effects),
    }
    if args.get("include_side_effects"):
        output["side_effects"] = matching_effects
    if expect_count is not None:
        output["decision"] = "pass" if len(matching_effects) == int(expect_count) else "fail"
    return output


def verify_audit(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    fixture_ref, payload = _payload_from_fixture(ctx, args)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    tampered = bool(args.get("tampered", False)) or "tampered" in text.lower()
    valid = not tampered
    return {
        "fixture_ref": fixture_ref,
        "audit_chain_valid": valid,
        "decision": "invalid" if not valid else "pass",
        "reason": "tamper marker detected" if not valid else "audit fixture is internally consistent",
    }


def replay_trace(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    expected = args.get("expected_decision", "allow")
    observed = args.get("observed_decision", expected)
    return {
        "replay_consistent": observed == expected,
        "decision": "pass" if observed == expected else "invalid",
        "expected_decision": expected,
        "observed_decision": observed,
    }


def tamper_audit_copy(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    side_effect = ctx.state.record_side_effect(
        ctx.trace_id,
        "audit",
        "tamper_audit_copy",
        args,
        committed=True,
        metadata={"tamper_type": args.get("tamper_type", "modify_decision")},
    )
    return {"tampered_copy": True, "decision": "invalid", "side_effect": side_effect}


P1_READ_TOOL_KINDS: dict[str, str] = {
    "list_calendar_events": "calendar_events",
    "list_tasks": "tasks",
    "search_employee_directory": "employee_directory",
    "query_hr_profile": "hr_profile",
    "query_invoice": "invoice",
    "get_deploy_status": "deploy_status",
    "query_customer_account": "customer_account",
    "list_repositories": "repositories",
    "read_repo_file": "repo_file",
    "scan_dependencies": "dependencies",
    "review_plugin_permissions": "plugin_permissions",
    "list_agents": "agents",
}


P1_WRITE_TOOL_SINKS: dict[str, str] = {
    "create_calendar_event": "calendar",
    "update_calendar_event": "calendar",
    "delete_calendar_event": "calendar",
    "create_task": "task",
    "complete_task": "task",
    "update_hr_case": "hr",
    "submit_time_off_request": "hr",
    "approve_time_off_request": "hr",
    "create_invoice": "finance",
    "approve_invoice": "finance",
    "issue_refund": "finance",
    "reconcile_expense": "finance",
    "create_release": "release",
    "approve_release": "release",
    "rollback_release": "release",
    "schedule_maintenance": "maintenance",
    "update_crm_note": "customer",
    "create_support_ticket": "support",
    "update_support_ticket": "support",
    "call_business_api": "business_api",
    "publish_artifact": "artifact",
    "sign_artifact": "artifact",
    "quarantine_plugin": "plugin",
    "register_agent": "agent_registry",
    "delegate_task": "agent_delegation",
    "grant_capability": "agent_capability",
    "revoke_capability": "agent_capability",
    "propose_policy_copy_update": "policy_copy",
    "publish_policy_copy": "policy_copy",
}


def _synthetic_read_tool(ctx: ToolContext, args: dict[str, Any], tool_name: str, kind: str) -> dict[str, Any]:
    fixture_ref, payload = _payload_from_fixture(ctx, args)
    return {
        "tool": tool_name,
        "kind": kind,
        "fixture_ref": fixture_ref,
        "content": payload,
        "classification": args.get("classification", "INTERNAL"),
        "synthetic": True,
    }


def _synthetic_side_effect_tool(ctx: ToolContext, args: dict[str, Any], tool_name: str, sink_type: str) -> dict[str, Any]:
    payload = _payload_with_context(ctx, args)
    side_effect = ctx.state.record_side_effect(
        ctx.trace_id,
        sink_type,
        tool_name,
        payload,
        committed=True,
        metadata={
            "synthetic": True,
            "target": args.get("target") or args.get("id") or args.get("name"),
        },
    )
    return {
        "recorded": True,
        "synthetic": True,
        "sink_type": sink_type,
        "operation": tool_name,
        "side_effect": side_effect,
    }


def _make_p1_read_handler(tool_name: str, kind: str) -> ToolHandler:
    def handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return _synthetic_read_tool(ctx, args, tool_name, kind)

    return handler


def _make_p1_write_handler(tool_name: str, sink_type: str) -> ToolHandler:
    def handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return _synthetic_side_effect_tool(ctx, args, tool_name, sink_type)

    return handler


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "read_mail": read_mail,
    "send_email": send_email,
    "send_notification": send_notification,
    "read_policy_doc": read_policy_doc,
    "submit_approval": submit_approval,
    "get_cpu": get_cpu,
    "read_log": read_log,
    "restart_service": restart_service,
    "exec_command": exec_command,
    "submit_change_ticket": submit_change_ticket,
    "query_project": query_project,
    "query_contract": query_contract,
    "query_employee_record": query_employee_record,
    "export_report": export_report,
    "search_rag": search_rag,
    "submit_payment_request": submit_payment_request,
    "list_plugins": list_plugins,
    "inspect_plugin": inspect_plugin,
    "install_plugin": install_plugin,
    "scan_aibom": scan_aibom,
    "run_ci_job": run_ci_job,
    "list_traces": list_traces,
    "verify_audit": verify_audit,
    "replay_trace": replay_trace,
    "tamper_audit_copy": tamper_audit_copy,
}

TOOL_HANDLERS.update(
    {tool_name: _make_p1_read_handler(tool_name, kind) for tool_name, kind in P1_READ_TOOL_KINDS.items()}
)
TOOL_HANDLERS.update(
    {tool_name: _make_p1_write_handler(tool_name, sink_type) for tool_name, sink_type in P1_WRITE_TOOL_SINKS.items()}
)


def execute_tool(ctx: ToolContext, tool_name: str, args: dict[str, Any]) -> ToolResult:
    if tool_name not in TOOL_HANDLERS:
        raise KeyError(f"unknown tool: {tool_name}")

    before = len(ctx.state.side_effects)
    output = TOOL_HANDLERS[tool_name](ctx, args)
    side_effects = ctx.state.side_effects[before:]
    side_effect_refs = [f"{effect['sink_type']}:{effect['operation']}:{index}" for index, effect in enumerate(side_effects, start=before)]
    decision = str(output.get("decision", "allow"))
    reason = str(output.get("reason", f"{tool_name} executed by null adapter"))
    ctx.state.record_audit(
        trace_id=ctx.trace_id,
        case_id=ctx.case_id,
        principal_id=ctx.principal_id,
        agent_id=ctx.agent_id,
        tool_name=tool_name,
        decision=decision,
        reason=reason,
        input_payload=args,
        output_payload=output,
        downstream_effect=side_effects,
    )
    ctx.state.remember_context(ctx.trace_id, tool_name, output)
    return ToolResult(tool_name=tool_name, output=output, side_effect_refs=side_effect_refs)
