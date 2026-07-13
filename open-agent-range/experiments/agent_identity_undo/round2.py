"""Round-2 feasibility: HTTP bearer binding plus encrypted restart-safe undo."""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
OAR_ROOT = REPO_ROOT / "open-agent-range"
for import_root in (REPO_ROOT / "src", REPO_ROOT, OAR_ROOT):
    value = str(import_root)
    if value not in sys.path:
        sys.path.insert(0, value)

import httpx  # noqa: E402
from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware  # noqa: E402
from mcp.server.auth.middleware.bearer_auth import (  # noqa: E402
    AuthenticatedUser,
    BearerAuthBackend,
    RequireAuthMiddleware,
)
from mcp.server.auth.provider import AccessToken  # noqa: E402
from starlette.middleware.authentication import AuthenticationMiddleware  # noqa: E402

from kernel.demo import reference_surface  # noqa: E402
from kernel.ledger import Ledger  # noqa: E402
from kernel.world import Principal, Receiver, World  # noqa: E402
from xa_guard.audit.merkle import ChainStore  # noqa: E402
from xa_guard.proxy.upstream import _build_streamable_http_asgi_app  # noqa: E402

from experiments.agent_identity_undo.round2_store import (  # noqa: E402
    DurableEffect,
    EncryptedEffectStore,
    RecoveryDecryptError,
)
from experiments.agent_identity_undo.vertical_slice import (  # noqa: E402
    AGENT_ID,
    ALICE,
    AUDIENCE,
    CAROL,
    EXTERNAL_RECEIVER,
    TARGET_SEAT,
    TENANT,
    ExperimentIdentityAuthority,
    IdentityError,
    _build_pipeline,
    _canonical,
    _forge_signature,
    _sha256,
)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class ExperimentTokenVerifier:
    """MCP TokenVerifier backed by the round-1 Ed25519 experiment authority."""

    def __init__(self, authority: ExperimentIdentityAuthority) -> None:
        self.authority = authority

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = self.authority.verify(token)
        except IdentityError:
            return None
        return AccessToken(
            token=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            client_id=claims.agent_id,
            scopes=list(claims.scopes),
            expires_at=claims.expires_at,
            resource=AUDIENCE,
            subject=claims.human_principal,
            claims={
                "iss": claims.issuer,
                "act": {"sub": claims.agent_id},
                "tenant_id": claims.tenant_id,
                "task_id": claims.task_id,
                "tools": list(claims.tools),
                "data_domains": list(claims.data_domains),
                "permissions": list(claims.permissions),
                "kid": claims.kid,
                "jti_sha256": claims.jti_sha256,
            },
        )


class IdentityBindingMiddleware:
    """Bind verified HTTP bearer claims to tools/call governance envelope."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return

        body_parts: list[bytes] = []
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            if message.get("type") != "http.request":
                continue
            body_parts.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        body = b"".join(body_parts)

        replayed = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        try:
            payload = json.loads(body or b"{}")
        except (TypeError, ValueError):
            await self.app(scope, replay_receive, send)
            return
        if payload.get("method") != "tools/call":
            await self.app(scope, replay_receive, send)
            return

        user = scope.get("user")
        if not isinstance(user, AuthenticatedUser):
            await _send_json_error(send, 401, "invalid_token", "verified bearer identity is required")
            return
        token = user.access_token
        claims = token.claims or {}
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        tool_name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        envelope = arguments.get("_xa_guard") if isinstance(arguments.get("_xa_guard"), dict) else {}
        error = _binding_error(token, claims, tool_name, envelope)
        if error:
            await _send_json_error(send, 403, "identity_context_mismatch", error)
            return
        await self.app(scope, replay_receive, send)


def _binding_error(
    token: AccessToken,
    claims: dict[str, Any],
    tool_name: str,
    envelope: dict[str, Any],
) -> str:
    actor = claims.get("act") if isinstance(claims.get("act"), dict) else {}
    expected = {
        "human_principal": str(token.subject or ""),
        "agent_id": str(actor.get("sub") or ""),
        "tenant_id": str(claims.get("tenant_id") or ""),
    }
    if not envelope:
        return "governance envelope is required"
    for key, value in expected.items():
        if str(envelope.get(key) or "") != value:
            return f"{key} conflicts with verified bearer identity"
    tools = {str(item) for item in claims.get("tools", []) or []}
    if tool_name not in tools:
        return f"tool {tool_name} is outside bearer scope"
    data_domain = str(envelope.get("data_domain") or "")
    domains = {str(item) for item in claims.get("data_domains", []) or []}
    if data_domain and data_domain not in domains:
        return f"data domain {data_domain} is outside bearer scope"
    return ""


async def _send_json_error(send: Any, status: int, error: str, description: str) -> None:
    body = json.dumps({"error": error, "error_description": description}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class OARRouter:
    """Duck-typed downstream router that executes the real OAR ToolSurface."""

    def __init__(self, world: World, ledger: Ledger) -> None:
        self.world = world
        self.ledger = ledger
        self.surface = reference_surface()
        self.executor_calls = 0

    def list_tools(self) -> list[dict[str, Any]]:
        tool = self.surface.get("update_registry")
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
        ]

    async def call_tool(self, ctx: Any) -> Any:
        self.executor_calls += 1
        return self.surface.execute(
            ctx.tool_name,
            self.world,
            self.ledger,
            ctx.human_principal,
            dict(ctx.arguments or {}),
        )


def _world() -> World:
    return World(
        principals={
            ALICE: Principal(principal_id=ALICE, role="agent_operator", domain="Platform"),
            CAROL: Principal(principal_id=CAROL, role="security_approver", domain="Security"),
        },
        receivers={
            EXTERNAL_RECEIVER: Receiver(
                receiver_id=EXTERNAL_RECEIVER,
                external=True,
                kind="synthetic public recipient",
            )
        },
        domain_state={
            "registry": {
                TARGET_SEAT: {"owner": "platform-team-round2", "status": "active", "updated_ts": 0}
            },
            "clock": {"current_ts": 0},
        },
    )


def _protected_app(inner: Any, authority: ExperimentIdentityAuthority) -> Any:
    app: Any = IdentityBindingMiddleware(inner)
    app = RequireAuthMiddleware(app, required_scopes=["xa.invoke"])
    app = AuthContextMiddleware(app)
    app = AuthenticationMiddleware(app, backend=BearerAuthBackend(ExperimentTokenVerifier(authority)))
    return app


def _envelope(principal: str, data_domain: str = "agent_registry") -> dict[str, Any]:
    return {
        "tenant_id": TENANT,
        "human_principal": principal,
        "agent_id": AGENT_ID,
        "data_domain": data_domain,
    }


async def _call_mcp(app: Any, *, token: str, arguments: dict[str, Any]) -> Any:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as http_client:
        async with streamable_http_client(
            "http://testserver/mcp",
            http_client=http_client,
        ) as (read_stream, write_stream, _get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await session.call_tool("update_registry", arguments)


async def _raw_case(
    app: Any,
    *,
    token: str | None,
    tool_name: str,
    envelope: dict[str, Any],
) -> dict[str, Any]:
    transport = httpx.ASGITransport(app=app)
    headers = {"Accept": "application/json, text/event-stream"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": {
                "seat_id": TARGET_SEAT,
                "owner": "attacker",
                "status": "disabled",
                "_xa_guard": envelope,
            },
        },
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/mcp", headers=headers, json=payload)
    try:
        body = response.json()
    except ValueError:
        body = {"text": response.text}
    return {"status_code": response.status_code, "body": body}


def _append_ledger_effect(
    ledger: Ledger,
    *,
    action: str,
    effect_id: str,
    principal: str,
    trace_id: str,
    decision: str,
) -> None:
    ledger.append(
        actor="XA-Guard round2 feasibility",
        principal=principal,
        role="security-control-plane",
        action=action,
        tool="update_registry",
        data_ref=effect_id,
        classification="INTERNAL",
        decision=decision,
        identity_chain=[{"original_principal": principal, "principal": principal}],
        metadata={"trace_id": trace_id, "effect_id": effect_id},
    )


def _write_manifest(output_dir: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if (
            not path.is_file()
            or path.name == "artifact-hashes.json"
            or path.name.endswith(("-wal", "-shm"))
        ):
            continue
        manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    _write_json(output_dir / "artifact-hashes.json", manifest)
    return manifest


async def _run(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    authority = ExperimentIdentityAuthority()
    alice_token = authority.mint(
        human_principal=ALICE,
        tools=["update_registry"],
        data_domains=["agent_registry"],
        permissions=["undo.request"],
    )
    carol_token = authority.mint(
        human_principal=CAROL,
        tools=["update_registry"],
        data_domains=["agent_registry"],
        permissions=["undo.approve"],
    )
    world = _world()
    ledger = Ledger(output_dir / "ledger.jsonl")
    router = OARRouter(world, ledger)
    pipeline = _build_pipeline(output_dir)
    inner = _build_streamable_http_asgi_app(
        pipeline,
        router,
        host="testserver",
        port=80,
        session_idle_timeout_seconds=30,
    )
    app = _protected_app(inner, authority)

    _write_json(output_dir / "world-before.json", world.to_dict())
    target_before = copy.deepcopy(world.domain_state["registry"][TARGET_SEAT])
    calls_before_negative = router.executor_calls
    async with inner.router.lifespan_context(inner):
        negative_cases = {
            "missing_bearer": await _raw_case(
                app,
                token=None,
                tool_name="update_registry",
                envelope=_envelope(ALICE),
            ),
            "bad_signature": await _raw_case(
                app,
                token=_forge_signature(alice_token),
                tool_name="update_registry",
                envelope=_envelope(ALICE),
            ),
            "identity_conflict": await _raw_case(
                app,
                token=alice_token,
                tool_name="update_registry",
                envelope=_envelope("mallory@dctg.local"),
            ),
            "tool_scope": await _raw_case(
                app,
                token=alice_token,
                tool_name="send_message",
                envelope=_envelope(ALICE),
            ),
        }
        negative_executor_calls = router.executor_calls - calls_before_negative

        await _call_mcp(
            app,
            token=alice_token,
            arguments={
                "seat_id": TARGET_SEAT,
                "owner": ALICE,
                "status": "disabled",
                "_xa_guard": _envelope(ALICE),
            },
        )
        target_after = copy.deepcopy(world.domain_state["registry"][TARGET_SEAT])
        _write_json(output_dir / "world-after-action.json", world.to_dict())
        audit_rows = _read_jsonl(output_dir / "audit.jsonl")
        original_trace = str(audit_rows[-1]["trace_id"])
        effect_id = f"effect-r2-{original_trace[:12]}"
        _append_ledger_effect(
            ledger,
            action="effect_recorded",
            effect_id=effect_id,
            principal=ALICE,
            trace_id=original_trace,
            decision="allow",
        )

        key = os.urandom(32)
        key_id = f"round2-{hashlib.sha256(key).hexdigest()[:16]}"
        db_path = output_dir / "effects.sqlite3"
        store = EncryptedEffectStore(db_path, key=key, key_id=key_id)
        effect = DurableEffect(
            effect_id=effect_id,
            tenant_id=TENANT,
            trace_id=original_trace,
            principal=ALICE,
            agent_id=AGENT_ID,
            tool_name="update_registry",
            reversibility="reversible",
            before_sha256=_sha256(target_before),
            after_sha256=_sha256(target_after),
        )
        store.create_effect(effect, {"registry_entry": target_before})
        store.checkpoint()

        restarted_store = EncryptedEffectStore(db_path, key=key, key_id=key_id)
        recovered = restarted_store.decrypt_recovery(effect_id)
        wrong_key_rejected = False
        try:
            wrong = EncryptedEffectStore(db_path, key=os.urandom(32), key_id=key_id)
            wrong.decrypt_recovery(effect_id)
        except RecoveryDecryptError:
            wrong_key_rejected = True

        idempotency_key = "round2-restore-agent-seat-01"
        request_id_1, created_1 = restarted_store.request_undo(
            effect_id,
            requester=ALICE,
            idempotency_key=idempotency_key,
        )
        request_id_2, created_2 = restarted_store.request_undo(
            effect_id,
            requester=ALICE,
            idempotency_key=idempotency_key,
        )
        self_claim = restarted_store.claim_compensation(request_id_1, approver=ALICE)

        contender_a = EncryptedEffectStore(db_path, key=key, key_id=key_id)
        contender_b = EncryptedEffectStore(db_path, key=key, key_id=key_id)
        claims = await asyncio.gather(
            asyncio.to_thread(contender_a.claim_compensation, request_id_1, approver=CAROL),
            asyncio.to_thread(contender_b.claim_compensation, request_id_1, approver=CAROL),
        )
        concurrent_claim_count = sum(1 for item in claims if item.claimed)
        if concurrent_claim_count != 1:
            raise RuntimeError(f"expected one compensation claimant, got {concurrent_claim_count}")

        recovery_entry = recovered["registry_entry"]
        await _call_mcp(
            app,
            token=carol_token,
            arguments={
                "seat_id": TARGET_SEAT,
                "owner": recovery_entry["owner"],
                "status": recovery_entry["status"],
                "compensates_effect_id": effect_id,
                "_xa_guard": _envelope(CAROL),
            },
        )
        audit_rows = _read_jsonl(output_dir / "audit.jsonl")
        compensation_trace = str(audit_rows[-1]["trace_id"])
        restarted_store.complete_compensation(
            request_id_1,
            compensation_trace_id=compensation_trace,
            succeeded=True,
        )
        _append_ledger_effect(
            ledger,
            action="compensation_completed",
            effect_id=effect_id,
            principal=CAROL,
            trace_id=compensation_trace,
            decision="allow",
        )

    final_store = EncryptedEffectStore(db_path, key=key, key_id=key_id)
    final_store.checkpoint()
    final_effect = final_store.get_effect(effect_id)
    final_store.export_events(output_dir / "effect-events.jsonl")
    _write_json(output_dir / "world-after-undo.json", world.to_dict())
    _write_json(output_dir / "http-negative-cases.json", negative_cases)

    audit_chain_ok, audit_bad_line = ChainStore(output_dir / "audit.jsonl", algo="sha256").verify()
    ledger_chain_ok = ledger.verify_hash_chain()
    effect_event_chain_ok = final_store.verify_event_chain()
    db_bytes = db_path.read_bytes()
    db_plaintext_absent = _canonical(target_before) not in db_bytes and target_before["owner"].encode() not in db_bytes
    artifact_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            output_dir / "audit.jsonl",
            output_dir / "ledger.jsonl",
            output_dir / "effect-events.jsonl",
            output_dir / "http-negative-cases.json",
        ]
    )
    raw_tokens_absent = alice_token not in artifact_text and carol_token not in artifact_text
    http_statuses_correct = {
        name: result["status_code"] for name, result in negative_cases.items()
    } == {
        "missing_bearer": 401,
        "bad_signature": 401,
        "identity_conflict": 403,
        "tool_scope": 403,
    }
    state_restored = world.domain_state["registry"][TARGET_SEAT] == target_before
    checks = {
        "http_statuses_correct": http_statuses_correct,
        "negative_executor_calls": negative_executor_calls,
        "valid_http_action_executed": target_after != target_before,
        "restart_recovery_matches": recovered == {"registry_entry": target_before},
        "wrong_key_rejected": wrong_key_rejected,
        "db_plaintext_absent": db_plaintext_absent,
        "idempotent_request": request_id_1 == request_id_2 and created_1 and not created_2,
        "self_approval_denied": not self_claim.claimed and self_claim.reason == "self_approval",
        "concurrent_single_claim": concurrent_claim_count == 1,
        "state_restored": state_restored,
        "durable_compensated_status": final_effect["status"] == "compensated"
        and final_effect["compensation_trace_id"] == compensation_trace,
        "compensation_trace_distinct": compensation_trace != original_trace,
        "audit_chain_ok": audit_chain_ok,
        "ledger_chain_ok": ledger_chain_ok,
        "effect_event_chain_ok": effect_event_chain_ok,
        "raw_tokens_absent": raw_tokens_absent,
    }
    go = checks["negative_executor_calls"] == 0 and all(
        value is True for key_name, value in checks.items() if key_name != "negative_executor_calls"
    )
    conclusion = "ROUND2-GO" if go else "NO-GO"
    events = final_store.events()
    summary = {
        "schema_version": "xa-guard-identity-undo-feasibility-round2/v0.1",
        "conclusion": conclusion,
        "checks": checks,
        "http_negative_cases": negative_cases,
        "traces": {"original_action": original_trace, "compensation": compensation_trace},
        "effect": final_effect,
        "counts": {
            "executor_calls": router.executor_calls,
            "audit_records": len(_read_jsonl(output_dir / "audit.jsonl")),
            "ledger_entries": len(ledger.entries),
            "effect_events": len(events),
            "compensation_started_events": sum(
                1 for event in events if event["event_type"] == "compensation_started"
            ),
        },
        "audit_bad_line": audit_bad_line,
        "public_key_sha256": authority.public_key_sha256,
        "effect_key_id": key_id,
        "limitations": [
            "local in-memory issuer; no production IdP, OIDC discovery, JWKS rotation, or revocation",
            "experimental outer ASGI middleware; XA-Guard production upstream is unchanged",
            "single-node SQLite and caller-supplied AES key; no KMS/HSM or multi-host consensus",
            "one synthetic registry compensation; no generic connector or failure-retry scheduler",
        ],
    }
    _write_json(output_dir / "summary.json", summary)
    _write_json(
        output_dir / "environment.json",
        {
            "python": sys.version,
            "platform": platform.platform(),
            "implementation": platform.python_implementation(),
            "repo_root": str(REPO_ROOT),
        },
    )
    (output_dir / "commands.txt").write_text(
        "$env:PYTHONPATH='src;open-agent-range;.'\n"
        "python open-agent-range/experiments/agent_identity_undo/round2.py "
        "--out docs/evidence/agent-identity-undo-spike-round2-2026-07-12\n",
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        "# Agent Identity + Undo round-2 feasibility evidence\n\n"
        f"Conclusion: **{conclusion}**\n\n"
        "This package exercises a real Streamable HTTP MCP session protected by an experimental "
        "Bearer identity binder, then persists encrypted recovery material in SQLite and proves "
        "restart recovery, idempotency, separation of duty, and single-winner concurrent claim.\n\n"
        "It is not production OAuth/OIDC, KMS-backed storage, distributed Saga orchestration, "
        "or a universal undo guarantee. No private key, AES key, or complete Bearer token is persisted.\n",
        encoding="utf-8",
    )
    _write_manifest(output_dir)
    return summary


def run_round2(output_dir: str | Path) -> dict[str, Any]:
    return asyncio.run(_run(Path(output_dir).resolve()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="new evidence directory; must not already exist")
    args = parser.parse_args(argv)
    summary = run_round2(args.out)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["conclusion"] == "ROUND2-GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
