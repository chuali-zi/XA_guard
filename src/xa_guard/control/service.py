"""Single application service used by REST control endpoints and the worker."""

from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable

from xa_guard.approval import issue_approval
from xa_guard.control.business import BusinessClient, BusinessError
from xa_guard.control.ceiling import GovernanceCeiling
from xa_guard.control.contracts import ContractRegistry, contract_succeeded, resolve_pointer
from xa_guard.control.crypto import CryptoError, InternalAuthorization, sha256_json
from xa_guard.control.models import Principal
from xa_guard.control.store import AsyncEffectStore, AuthorizationError, ConflictError
from xa_guard.types import Decision, GateContext, InputSource


class ServiceError(RuntimeError):
    code = "service_error"


class ControlService:
    def __init__(
        self,
        *,
        store: AsyncEffectStore,
        business: BusinessClient,
        pipeline: Any,
        contracts: ContractRegistry,
        ceiling: GovernanceCeiling,
        internal_authorization: InternalAuthorization,
    ) -> None:
        self.store = store
        self.business = business
        self.pipeline = pipeline
        self.contracts = contracts
        self.ceiling = ceiling
        self.internal_authorization = internal_authorization

    async def me(self, principal: Principal) -> dict[str, Any]:
        assignments = await self.store.effective_assignments(principal)
        return {
            "subject": principal.subject,
            "username": principal.username,
            "tenant_id": principal.tenant_id,
            "agent_id": principal.agent_id,
            "roles": list(principal.roles),
            "groups": list(principal.groups),
            "available_agents": sorted({item["agent_id"] for item in assignments}),
            "assignment_version": max((item["version"] for item in assignments), default=0),
        }

    async def agents(self, principal: Principal) -> list[dict[str, Any]]:
        assignments = await self.store.effective_assignments(principal)
        result: list[dict[str, Any]] = []
        for assignment in assignments:
            ceiling = self.ceiling.agents.get(assignment["agent_id"])
            if ceiling is None:
                continue
            result.append(
                {
                    "agent_id": ceiling.agent_id,
                    "name": ceiling.name,
                    "purpose": ceiling.purpose,
                    "tools": assignment["tools"],
                    "data_domains": assignment["data_domains"],
                    "assignment_version": assignment["version"],
                }
            )
        return result

    async def create_ticket(self, principal: Principal, arguments: dict[str, Any]) -> dict[str, Any]:
        unexpected = set(arguments).difference({"title", "description", "priority", "data_domain"})
        if unexpected:
            raise ConflictError("ticket contains unsupported or identity-bearing fields")
        data_domain = str(arguments.get("data_domain") or "engineering_docs")
        arguments = {
            "title": str(arguments.get("title") or "").strip(),
            "description": str(arguments.get("description") or "").strip(),
            "priority": str(arguments.get("priority") or "normal"),
        }
        if not arguments["title"] or not arguments["description"]:
            raise ConflictError("ticket title and description are required")
        if arguments["priority"] not in {"low", "normal", "high", "urgent"}:
            raise ConflictError("ticket priority is invalid")
        await self.authorize(principal, "business_submit_ticket", data_domain)
        contract = self.contracts.for_tool("business_submit_ticket")
        if contract is None:
            raise ServiceError("business_submit_ticket contract is absent")
        ctx = self._context(principal, "business_submit_ticket", arguments, data_domain)

        async def execute(active: GateContext) -> Any:
            effect_id = await self.store.prepare_effect(
                principal=principal,
                trace_id=active.trace_id,
                data_domain=data_domain,
                args=arguments,
                contract=contract,
            )
            active.effect_id = effect_id
            active.side_effect_level = contract.side_effect_level
            active.reversibility = contract.reversibility
            active.undo_status = "prepared"
            try:
                response = await self.business.create_ticket(
                    effect_id=effect_id,
                    trace_id=active.trace_id,
                    tenant_id=principal.tenant_id,
                    arguments=arguments,
                )
            except BusinessError:
                # An ambiguous network result intentionally remains prepared;
                # the reconciler will query by effect_id before changing state.
                raise
            if not contract_succeeded(contract, response):
                await self.store.mark_prepared_manual(effect_id, "business_result_not_success")
                raise ServiceError("business API did not satisfy the effect success contract")
            root = {"input": arguments, "result": response}
            recovery = {name: resolve_pointer(root, pointer) for name, pointer in contract.recovery_fields.items()}
            reference = str((response.get("body") or {}).get("ticket_id") or "")
            await self.store.complete_effect(effect_id, principal, recovery, response, reference)
            active.undo_status = "available"
            return response

        result = await self._run_confirmed(ctx, execute, principal.username, "authenticated ticket submission")
        if not result.allowed:
            raise ServiceError("ticket creation was denied by XA-Guard")
        return {
            "trace_id": ctx.trace_id,
            "effect_id": ctx.effect_id,
            "undo_status": ctx.undo_status,
            "business": result.tool_result,
        }

    async def request_undo(
        self, principal: Principal, effect_id: str, reason: str, idempotency_key: str
    ) -> dict[str, Any]:
        if "undo.request" not in principal.roles:
            raise AuthorizationError("undo.request role is required")
        effect = await self.store.get_effect(principal.tenant_id, effect_id)
        await self.authorize(principal, effect["tool_name"], effect["data_domain"])
        value, created = await self.store.request_undo(effect_id, principal, reason, idempotency_key)
        return {**value, "created": created}

    async def decide_undo(
        self, principal: Principal, request_id: str, decision: str, reason: str
    ) -> dict[str, Any]:
        if "undo.approve" not in principal.roles:
            raise AuthorizationError("undo.approve role is required")
        request = await self.store.get_undo_request(principal.tenant_id, request_id)
        contract = dict(request["contract_snapshot"])
        compensation_tool = str(contract.get("compensation_tool") or "")
        await self.authorize(principal, compensation_tool, request["data_domain"])
        args_hash = sha256_json({"reason": reason})
        authorization = ""
        if decision == "approve":
            authorization = self.internal_authorization.issue(
                {
                    "effect_id": request["effect_id"],
                    "request_id": request_id,
                    "approver_sub": principal.subject,
                    "approver_username": principal.username,
                    "tenant_id": principal.tenant_id,
                    "agent_id": principal.agent_id,
                    "groups": list(principal.groups),
                    "roles": list(principal.roles),
                    "parameters": {"reason": reason},
                    "parameters_sha256": args_hash,
                }
            )
        return await self.store.decide_undo(
            request_id, principal, decision, reason, authorization, args_hash
        )

    async def retry_failed(self, principal: Principal, request_id: str) -> None:
        """Re-authorize a permanent failure under a current admin identity.

        The original approval remains the separation-of-duty decision.  The
        retry actor only receives a new, short-lived execution authorization;
        the stored signed parameters and all effect/request bindings are
        authenticated before they are copied.
        """

        if "undo.admin" not in principal.roles:
            raise AuthorizationError("undo.admin role is required")
        request = await self.store.get_undo_request(principal.tenant_id, request_id)
        contract = dict(request["contract_snapshot"])
        compensation_tool = str(contract.get("compensation_tool") or "")
        await self.authorize(principal, compensation_tool, request["data_domain"])
        token = str(request.get("internal_authorization") or "")
        args_hash = str(request.get("compensation_args_sha256") or "")
        try:
            claims = self.internal_authorization.verify_for_admin_retry(
                token,
                expected={
                    "effect_id": request["effect_id"],
                    "request_id": request_id,
                    "approver_sub": str(request.get("approver_sub") or ""),
                    "tenant_id": principal.tenant_id,
                    "parameters_sha256": args_hash,
                },
            )
        except CryptoError as exc:
            raise ConflictError("stored compensation authorization cannot be renewed") from exc
        parameters = claims.get("parameters")
        if not isinstance(parameters, dict) or sha256_json(parameters) != args_hash:
            raise ConflictError("stored compensation parameters cannot be renewed")
        renewed = self.internal_authorization.issue(
            {
                "effect_id": request["effect_id"],
                "request_id": request_id,
                "approver_sub": str(request["approver_sub"]),
                "approver_username": str(request["approver_username"]),
                "authorization_sub": principal.subject,
                "authorization_username": principal.username,
                "retry_actor_sub": principal.subject,
                "tenant_id": principal.tenant_id,
                "agent_id": principal.agent_id,
                "groups": list(principal.groups),
                "roles": list(principal.roles),
                "parameters": parameters,
                "parameters_sha256": args_hash,
            },
            ttl_seconds=900,
        )
        await self.store.retry_failed(
            principal.tenant_id,
            request_id,
            principal.subject,
            renewed,
            args_hash,
        )

    async def create_assignment(self, principal: Principal, value: dict[str, Any]) -> dict[str, Any]:
        if "governance.admin" not in principal.roles:
            raise AuthorizationError("governance.admin role is required")
        self.ceiling.validate_assignment(principal.tenant_id, value)
        ctx = self._context(principal, "grant_permission", value, "engineering_docs")
        result = await self._run_confirmed(
            ctx,
            lambda _ctx: self.store.create_assignment(principal, value),
            principal.username,
            "authenticated assignment change",
        )
        if not result.allowed:
            raise ServiceError("assignment change was denied by XA-Guard")
        return result.tool_result

    async def delete_assignment(self, principal: Principal, assignment_id: str, version: int) -> None:
        if "governance.admin" not in principal.roles:
            raise AuthorizationError("governance.admin role is required")
        ctx = self._context(
            principal,
            "grant_permission",
            {"assignment_id": assignment_id, "expected_version": version, "action": "revoke"},
            "engineering_docs",
        )

        async def execute(_ctx: GateContext) -> dict[str, Any]:
            await self.store.delete_assignment(principal, assignment_id, version)
            return {"assignment_id": assignment_id, "deleted": True}

        result = await self._run_confirmed(ctx, execute, principal.username, "authenticated assignment revocation")
        if not result.allowed:
            raise ServiceError("assignment revocation was denied by XA-Guard")

    async def reconcile_once(self) -> int:
        reconciled = 0
        for row in await self.store.list_prepared():
            try:
                response = await self.business.get_by_effect(effect_id=row["effect_id"], trace_id=row["trace_id"])
            except BusinessError as exc:
                if not exc.retryable and exc.code == "not_found":
                    await self.store.mark_prepared_manual(row["effect_id"], "reconcile_not_found")
                continue
            principal = Principal(
                subject=row["principal_sub"],
                username=row["principal_username"],
                tenant_id=row["tenant_id"],
                agent_id=row["agent_id"],
                issuer="internal-reconciler",
                token_id_hash="",
            )
            ticket_id = str((response.get("body") or {}).get("ticket_id") or "")
            if ticket_id:
                await self.store.complete_effect(row["effect_id"], principal, {"ticket_id": ticket_id}, response, ticket_id)
                reconciled += 1
        return reconciled

    async def authorize(self, principal: Principal, tool_name: str, data_domain: str) -> dict[str, Any]:
        agent = self.ceiling.agents.get(principal.agent_id)
        if agent is None or agent.tenant_id != principal.tenant_id:
            raise AuthorizationError("token agent is outside the governance ceiling")
        if tool_name not in agent.tools or data_domain not in agent.data_domains:
            raise AuthorizationError("operation is outside the current governance ceiling")
        return await self.store.authorize(principal, principal.agent_id, tool_name, data_domain)

    async def _run_confirmed(
        self,
        ctx: GateContext,
        executor: Callable[[GateContext], Awaitable[Any]],
        approver: str,
        reason: str,
    ) -> Any:
        result = await self.pipeline.run(ctx, executor)
        if result.final_decision == Decision.REQUIRE_APPROVAL:
            ctx.approval = issue_approval(
                trace_id=ctx.trace_id,
                tool_name=ctx.tool_name,
                arguments=ctx.arguments,
                approver=approver,
                reason=reason,
            )
            result = await self.pipeline.run_after_approval(ctx, executor)
        return result

    @staticmethod
    def _context(
        principal: Principal, tool_name: str, arguments: dict[str, Any], data_domain: str
    ) -> GateContext:
        return GateContext(
            trace_id=str(uuid.uuid4()),
            tool_name=tool_name,
            arguments=dict(arguments),
            input_sources=[InputSource.USER],
            tenant_id=principal.tenant_id,
            human_principal=principal.subject,
            agent_id=principal.agent_id,
            data_domain=data_domain,
            identity_verified=True,
            identity_issuer=principal.issuer,
            identity_jti_sha256=principal.token_id_hash,
            identity_scopes=list(principal.scopes),
        )
