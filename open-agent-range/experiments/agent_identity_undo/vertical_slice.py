"""Minimal trusted-identity plus compensating-undo feasibility vertical slice.

This experiment intentionally lives outside ``src/xa_guard``.  It composes the
real XA-Guard Pipeline/Governance/Gate6 implementation with the OAR synthetic
World/ToolSurface/Ledger.  It is evidence for a design decision, not a production
JWT issuer, OAuth resource server, durable Saga store, or generic undo engine.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import copy
import hashlib
import json
import platform
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
OAR_ROOT = REPO_ROOT / "open-agent-range"
for import_root in (REPO_ROOT / "src", REPO_ROOT, OAR_ROOT):
    value = str(import_root)
    if value not in sys.path:
        sys.path.insert(0, value)

from cryptography.exceptions import InvalidSignature  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from kernel.demo import reference_surface  # noqa: E402
from kernel.ledger import Ledger  # noqa: E402
from kernel.world import Principal, Receiver, World  # noqa: E402
from xa_guard.audit.merkle import ChainStore  # noqa: E402
from xa_guard.config import GateConfig, GovernanceConfig, XAGuardConfig  # noqa: E402
from xa_guard.gates.gate1_input import Gate1Input  # noqa: E402
from xa_guard.gates.gate2_plan import Gate2Plan  # noqa: E402
from xa_guard.gates.gate3_policy import Gate3Policy  # noqa: E402
from xa_guard.gates.gate4_taint import Gate4Taint  # noqa: E402
from xa_guard.gates.gate5_sandbox import Gate5Sandbox  # noqa: E402
from xa_guard.gates.gate6_audit import Gate6Audit  # noqa: E402
from xa_guard.governance import GovernanceEnforcer  # noqa: E402
from xa_guard.pipeline import Pipeline, PipelineResult  # noqa: E402
from xa_guard.types import Decision, GateContext, GateResult, InputSource  # noqa: E402


ISSUER = "https://identity.dctg.local/feasibility"
AUDIENCE = "xa-guard://identity-undo-spike"
TENANT = "dctg"
AGENT_ID = "open-agent-range"
ALICE = "alice.operator@dctg.local"
CAROL = "carol.security@dctg.local"
EXTERNAL_RECEIVER = "public.notice@example.test"
TARGET_SEAT = "agent-seat-01"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


class IdentityError(ValueError):
    """Stable experiment identity failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class VerifiedClaims:
    issuer: str
    human_principal: str
    agent_id: str
    tenant_id: str
    task_id: str
    tools: tuple[str, ...]
    data_domains: tuple[str, ...]
    permissions: tuple[str, ...]
    scopes: tuple[str, ...]
    expires_at: int
    kid: str
    jti_sha256: str


class ExperimentIdentityAuthority:
    """In-memory Ed25519 compact-JWS issuer/verifier for this experiment only."""

    def __init__(self, *, now: int | None = None) -> None:
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.now = int(now if now is not None else time.time())
        raw_public = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.kid = f"exp-ed25519-{hashlib.sha256(raw_public).hexdigest()[:16]}"
        self.public_key_sha256 = hashlib.sha256(raw_public).hexdigest()

    def mint(
        self,
        *,
        human_principal: str,
        tools: list[str],
        data_domains: list[str],
        permissions: list[str],
        audience: str = AUDIENCE,
        issued_at: int | None = None,
        expires_at: int | None = None,
    ) -> str:
        iat = int(self.now if issued_at is None else issued_at)
        exp = int(iat + 300 if expires_at is None else expires_at)
        payload = {
            "iss": ISSUER,
            "sub": human_principal,
            "act": {"sub": AGENT_ID},
            "aud": audience,
            "iat": iat,
            "nbf": iat - 1,
            "exp": exp,
            "jti": f"jti-{human_principal}-{iat}-{exp}",
            "tenant_id": TENANT,
            "task_id": "identity-undo-feasibility",
            "tools": sorted(set(tools)),
            "data_domains": sorted(set(data_domains)),
            "permissions": sorted(set(permissions)),
            "scope": "xa.invoke",
        }
        header = {"alg": "EdDSA", "kid": self.kid, "typ": "JWT"}
        encoded_header = _b64url_encode(_canonical(header))
        encoded_payload = _b64url_encode(_canonical(payload))
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        signature = self.private_key.sign(signing_input)
        return f"{encoded_header}.{encoded_payload}.{_b64url_encode(signature)}"

    def verify(
        self,
        token: str,
        *,
        required_tool: str | None = None,
        now: int | None = None,
    ) -> VerifiedClaims:
        try:
            encoded_header, encoded_payload, encoded_signature = token.split(".")
            header = json.loads(_b64url_decode(encoded_header))
            payload = json.loads(_b64url_decode(encoded_payload))
            signature = _b64url_decode(encoded_signature)
        except Exception as exc:
            raise IdentityError("IDN-MALFORMED", "malformed compact JWS") from exc

        if header.get("alg") != "EdDSA" or header.get("kid") != self.kid:
            raise IdentityError("IDN-UNTRUSTED-KEY", "untrusted algorithm or key id")
        try:
            self.public_key.verify(signature, f"{encoded_header}.{encoded_payload}".encode("ascii"))
        except InvalidSignature as exc:
            raise IdentityError("IDN-BAD-SIGNATURE", "signature verification failed") from exc

        checked_at = int(self.now if now is None else now)
        if payload.get("iss") != ISSUER:
            raise IdentityError("IDN-BAD-ISSUER", "issuer mismatch")
        if payload.get("aud") != AUDIENCE:
            raise IdentityError("IDN-BAD-AUDIENCE", "audience mismatch")
        if int(payload.get("nbf", 0)) > checked_at or int(payload.get("exp", 0)) <= checked_at:
            raise IdentityError("IDN-EXPIRED", "credential is expired or not active")
        if int(payload.get("exp", 0)) - int(payload.get("iat", 0)) > 300:
            raise IdentityError("IDN-TTL", "credential lifetime exceeds experiment limit")

        human = str(payload.get("sub") or "")
        actor = payload.get("act") if isinstance(payload.get("act"), dict) else {}
        agent_id = str(actor.get("sub") or "")
        tenant = str(payload.get("tenant_id") or "")
        tools = tuple(str(item) for item in payload.get("tools", []) or [])
        if not human or not agent_id or not tenant:
            raise IdentityError("IDN-MISSING-SUBJECT", "human, agent, or tenant claim is missing")
        if agent_id != AGENT_ID:
            raise IdentityError("IDN-AGENT-MISMATCH", "agent workload identity mismatch")
        if required_tool is not None and required_tool not in tools:
            raise IdentityError("IDN-TOOL-SCOPE", f"credential does not allow tool {required_tool}")

        return VerifiedClaims(
            issuer=ISSUER,
            human_principal=human,
            agent_id=agent_id,
            tenant_id=tenant,
            task_id=str(payload.get("task_id") or ""),
            tools=tools,
            data_domains=tuple(str(item) for item in payload.get("data_domains", []) or []),
            permissions=tuple(str(item) for item in payload.get("permissions", []) or []),
            scopes=tuple(str(payload.get("scope") or "").split()),
            expires_at=int(payload.get("exp", 0)),
            kid=self.kid,
            jti_sha256=hashlib.sha256(str(payload.get("jti") or "").encode("utf-8")).hexdigest(),
        )


@dataclass
class EffectRecord:
    effect_id: str
    trace_id: str
    principal: str
    agent_id: str
    tool_name: str
    reversibility: str
    before_sha256: str
    after_sha256: str
    status: str
    compensation_trace_id: str = ""


class EffectJournal:
    """Small append-only experiment journal; not the proposed durable store."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.events: list[dict[str, Any]] = []

    def append(self, event: str, effect: EffectRecord, **extra: Any) -> dict[str, Any]:
        row = {
            "seq": len(self.events) + 1,
            "event": event,
            "effect": asdict(effect),
            **extra,
        }
        self.events.append(row)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row


@dataclass
class CallOutcome:
    result: PipelineResult
    claims: VerifiedClaims | None


class ExperimentRuntime:
    def __init__(self, *, output_dir: Path, authority: ExperimentIdentityAuthority) -> None:
        self.output_dir = output_dir
        self.authority = authority
        self.surface = reference_surface()
        self.world = World(
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
                    TARGET_SEAT: {
                        "owner": "platform-team",
                        "status": "active",
                        "updated_ts": 0,
                    }
                },
                "clock": {"current_ts": 0},
            },
        )
        self.ledger = Ledger(output_dir / "ledger.jsonl")
        self.executor_calls = 0
        self.pipeline = _build_pipeline(output_dir)

    async def call(
        self,
        *,
        token: str,
        tool_name: str,
        arguments: dict[str, Any],
        envelope: dict[str, Any],
    ) -> CallOutcome:
        try:
            claims = self.authority.verify(token, required_tool=tool_name)
            _check_envelope(claims, envelope)
        except IdentityError as exc:
            ctx = GateContext(
                tool_name=tool_name,
                arguments=dict(arguments),
                input_sources=[InputSource.USER],
                capability_token_summary={"token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest()},
            )
            ctx.append(
                GateResult(
                    gate_name="experiment_identity",
                    decision=Decision.DENY,
                    risks=[str(exc)],
                    rule_hits=[exc.code],
                    metadata={"decision_reason_code": exc.code},
                )
            )
            return CallOutcome(await self.pipeline.run(ctx, self._execute), None)

        safe_arguments = dict(arguments)
        safe_arguments["identity_chain"] = [
            {
                "original_principal": claims.human_principal,
                "principal": claims.human_principal,
                "agent_id": claims.agent_id,
                "issuer": claims.issuer,
                "kid": claims.kid,
            }
        ]
        ctx = GateContext(
            tool_name=tool_name,
            arguments=safe_arguments,
            input_sources=[InputSource.USER],
            tenant_id=claims.tenant_id,
            human_principal=claims.human_principal,
            agent_id=claims.agent_id,
            data_domain=str(envelope.get("data_domain") or ""),
            resource_owner=str(envelope.get("resource_owner") or ""),
            task_id=claims.task_id,
            capability_token_summary={
                "verification": "experiment-ed25519",
                "kid": claims.kid,
                "jti_sha256": claims.jti_sha256,
            },
        )
        ctx.append(
            GateResult(
                gate_name="experiment_identity",
                decision=Decision.ALLOW,
                rule_hits=["IDN-EXPERIMENT-VERIFIED"],
                metadata={"issuer": claims.issuer, "kid": claims.kid},
            )
        )
        return CallOutcome(await self.pipeline.run(ctx, self._execute), claims)

    async def _execute(self, ctx: GateContext) -> object:
        self.executor_calls += 1
        return self.surface.execute(
            ctx.tool_name,
            self.world,
            self.ledger,
            ctx.human_principal,
            dict(ctx.arguments),
        )


def _check_envelope(claims: VerifiedClaims, envelope: dict[str, Any]) -> None:
    requested_human = str(
        envelope.get("human_principal")
        or envelope.get("principal_id")
        or envelope.get("principal")
        or ""
    )
    requested_agent = str(envelope.get("agent_id") or "")
    requested_tenant = str(envelope.get("tenant_id") or envelope.get("tenant") or "")
    if requested_human and requested_human != claims.human_principal:
        raise IdentityError("IDN-CONTEXT-MISMATCH", "human principal conflicts with signed credential")
    if requested_agent and requested_agent != claims.agent_id:
        raise IdentityError("IDN-CONTEXT-MISMATCH", "agent identity conflicts with signed credential")
    if requested_tenant and requested_tenant != claims.tenant_id:
        raise IdentityError("IDN-CONTEXT-MISMATCH", "tenant conflicts with signed credential")
    data_domain = str(envelope.get("data_domain") or "")
    if data_domain and data_domain not in claims.data_domains:
        raise IdentityError("IDN-DATA-SCOPE", "data domain is outside signed credential scope")


def _build_pipeline(output_dir: Path) -> Pipeline:
    registry_path = Path(__file__).with_name("registry.yaml")
    capabilities_path = Path(__file__).with_name("tool_capabilities.yaml")
    cfg = XAGuardConfig(
        governance=GovernanceConfig(
            enabled=True,
            registry_file=str(registry_path),
            default_tenant=TENANT,
        )
    )
    return Pipeline(
        gate1=Gate1Input(cfg.gate("gate1")),
        gate2=Gate2Plan(cfg.gate("gate2")),
        gate3=Gate3Policy(cfg.gate("gate3")),
        gate4=Gate4Taint(
            GateConfig(options={"tool_capabilities_file": str(capabilities_path)})
        ),
        gate5=Gate5Sandbox(cfg.gate("gate5")),
        gate6=Gate6Audit(GateConfig(options={"audit_dir": str(output_dir), "hash_algo": "sha256"})),
        cfg=cfg,
        governance=GovernanceEnforcer(cfg.governance),
    )


def _forge_signature(token: str) -> str:
    parts = token.split(".")
    signature = bytearray(_b64url_decode(parts[-1]))
    if not signature:
        raise ValueError("cannot forge an empty signature")
    signature[0] ^= 0x01
    parts[-1] = _b64url_encode(bytes(signature))
    return ".".join(parts)


def _append_effect_fact(
    runtime: ExperimentRuntime,
    *,
    action: str,
    effect: EffectRecord,
    principal: str,
    decision: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    runtime.ledger.append(
        actor="XA-Guard feasibility",
        principal=principal,
        role="security-control-plane",
        action=action,
        tool=effect.tool_name,
        data_ref=effect.effect_id,
        classification="INTERNAL",
        decision=decision,
        identity_chain=[{"original_principal": effect.principal, "principal": principal}],
        metadata={"effect": asdict(effect), **(metadata or {})},
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_manifest(output_dir: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.name == "artifact-hashes.json":
            continue
        manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    _write_json(output_dir / "artifact-hashes.json", manifest)
    return manifest


async def _run(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    authority = ExperimentIdentityAuthority()
    runtime = ExperimentRuntime(output_dir=output_dir, authority=authority)
    journal = EffectJournal(output_dir / "effect-events.jsonl")
    now = authority.now

    alice_token = authority.mint(
        human_principal=ALICE,
        tools=["update_registry", "send_message"],
        data_domains=["agent_registry", "public_messaging"],
        permissions=["undo.request"],
    )
    carol_token = authority.mint(
        human_principal=CAROL,
        tools=["update_registry"],
        data_domains=["agent_registry"],
        permissions=["undo.approve"],
    )
    expired_token = authority.mint(
        human_principal=ALICE,
        tools=["update_registry"],
        data_domains=["agent_registry"],
        permissions=["undo.request"],
        issued_at=now - 301,
        expires_at=now - 1,
    )
    wrong_audience_token = authority.mint(
        human_principal=ALICE,
        tools=["update_registry"],
        data_domains=["agent_registry"],
        permissions=["undo.request"],
        audience="xa-guard://wrong-audience",
    )

    _write_json(output_dir / "world-before.json", runtime.world.to_dict())
    denied_before = runtime.executor_calls
    negative_cases = [
        (
            "bad_signature",
            _forge_signature(alice_token),
            {"tenant_id": TENANT, "human_principal": ALICE, "agent_id": AGENT_ID, "data_domain": "agent_registry"},
        ),
        (
            "expired",
            expired_token,
            {"tenant_id": TENANT, "human_principal": ALICE, "agent_id": AGENT_ID, "data_domain": "agent_registry"},
        ),
        (
            "wrong_audience",
            wrong_audience_token,
            {"tenant_id": TENANT, "human_principal": ALICE, "agent_id": AGENT_ID, "data_domain": "agent_registry"},
        ),
        (
            "self_report_conflict",
            alice_token,
            {
                "tenant_id": TENANT,
                "human_principal": "mallory@dctg.local",
                "agent_id": AGENT_ID,
                "data_domain": "agent_registry",
            },
        ),
    ]
    negative_results: dict[str, dict[str, Any]] = {}
    for name, token, envelope in negative_cases:
        outcome = await runtime.call(
            token=token,
            tool_name="update_registry",
            arguments={"seat_id": TARGET_SEAT, "owner": "attacker", "status": "disabled"},
            envelope=envelope,
        )
        negative_results[name] = {
            "allowed": outcome.result.allowed,
            "decision": outcome.result.final_decision.value,
            "reason": outcome.result.final_reason,
            "trace_id": outcome.result.ctx.trace_id,
        }
    denied_executor_count = runtime.executor_calls - denied_before

    target_before = copy.deepcopy(runtime.world.domain_state["registry"][TARGET_SEAT])
    action_outcome = await runtime.call(
        token=alice_token,
        tool_name="update_registry",
        arguments={"seat_id": TARGET_SEAT, "owner": ALICE, "status": "disabled"},
        envelope={
            "tenant_id": TENANT,
            "human_principal": ALICE,
            "agent_id": AGENT_ID,
            "data_domain": "agent_registry",
        },
    )
    target_after = copy.deepcopy(runtime.world.domain_state["registry"][TARGET_SEAT])
    _write_json(output_dir / "world-after-action.json", runtime.world.to_dict())
    effect = EffectRecord(
        effect_id=f"effect-{action_outcome.result.ctx.trace_id[:12]}",
        trace_id=action_outcome.result.ctx.trace_id,
        principal=ALICE,
        agent_id=AGENT_ID,
        tool_name="update_registry",
        reversibility="reversible",
        before_sha256=_sha256(target_before),
        after_sha256=_sha256(target_after),
        status="available",
    )
    journal.append("effect_recorded", effect)
    _append_effect_fact(
        runtime,
        action="effect_recorded",
        effect=effect,
        principal=ALICE,
        decision="allow",
        metadata={"trace_id": effect.trace_id},
    )

    effect.status = "undo_pending"
    journal.append("undo_requested", effect, requester=ALICE, reason="restore synthetic registry state")
    _append_effect_fact(runtime, action="undo_requested", effect=effect, principal=ALICE, decision="pending")

    alice_claims = authority.verify(alice_token, required_tool="update_registry")
    self_approval_denied = alice_claims.human_principal == effect.principal
    if self_approval_denied:
        journal.append("undo_approval_denied", effect, approver=ALICE, reason="separation_of_duty")
        _append_effect_fact(
            runtime,
            action="undo_approval_denied",
            effect=effect,
            principal=ALICE,
            decision="deny",
        )

    carol_claims = authority.verify(carol_token, required_tool="update_registry")
    if "undo.approve" not in carol_claims.permissions or carol_claims.human_principal == effect.principal:
        raise RuntimeError("experiment approver is not independently authorized")
    journal.append("compensation_started", effect, approver=CAROL)
    compensation_outcome = await runtime.call(
        token=carol_token,
        tool_name="update_registry",
        arguments={
            "seat_id": TARGET_SEAT,
            "owner": target_before["owner"],
            "status": target_before["status"],
            "compensates_effect_id": effect.effect_id,
        },
        envelope={
            "tenant_id": TENANT,
            "human_principal": CAROL,
            "agent_id": AGENT_ID,
            "data_domain": "agent_registry",
        },
    )
    effect.status = "compensated" if compensation_outcome.result.allowed else "compensation_failed"
    effect.compensation_trace_id = compensation_outcome.result.ctx.trace_id
    journal.append("compensation_completed", effect, approver=CAROL)
    _append_effect_fact(
        runtime,
        action="compensation_completed",
        effect=effect,
        principal=CAROL,
        decision="allow" if compensation_outcome.result.allowed else "deny",
        metadata={
            "trace_id": compensation_outcome.result.ctx.trace_id,
            "compensates_effect_id": effect.effect_id,
        },
    )
    _write_json(output_dir / "world-after-undo.json", runtime.world.to_dict())

    send_outcome = await runtime.call(
        token=alice_token,
        tool_name="send_message",
        arguments={"to": EXTERNAL_RECEIVER, "content": "synthetic public maintenance notice"},
        envelope={
            "tenant_id": TENANT,
            "human_principal": ALICE,
            "agent_id": AGENT_ID,
            "data_domain": "public_messaging",
        },
    )
    irreversible = EffectRecord(
        effect_id=f"effect-{send_outcome.result.ctx.trace_id[:12]}",
        trace_id=send_outcome.result.ctx.trace_id,
        principal=ALICE,
        agent_id=AGENT_ID,
        tool_name="send_message",
        reversibility="irreversible",
        before_sha256="",
        after_sha256=_sha256({"to": EXTERNAL_RECEIVER, "sent": send_outcome.result.allowed}),
        status="irreversible",
    )
    journal.append("effect_recorded", irreversible)
    _append_effect_fact(
        runtime,
        action="effect_recorded",
        effect=irreversible,
        principal=ALICE,
        decision="allow",
        metadata={"trace_id": irreversible.trace_id},
    )
    journal.append(
        "undo_manual_required",
        irreversible,
        requester=ALICE,
        warning="external message delivery cannot be truthfully reversed by this gateway",
    )
    _append_effect_fact(
        runtime,
        action="undo_manual_required",
        effect=irreversible,
        principal=ALICE,
        decision="manual_required",
    )

    audit_path = output_dir / "audit.jsonl"
    audit_chain_ok, audit_bad_line = ChainStore(audit_path, algo="sha256").verify()
    ledger_chain_ok = runtime.ledger.verify_hash_chain()
    target_restored = runtime.world.domain_state["registry"][TARGET_SEAT] == target_before
    raw_artifact_paths = [
        audit_path,
        output_dir / "ledger.jsonl",
        output_dir / "effect-events.jsonl",
        output_dir / "world-before.json",
        output_dir / "world-after-action.json",
        output_dir / "world-after-undo.json",
    ]
    raw_text = "\n".join(path.read_text(encoding="utf-8") for path in raw_artifact_paths)
    raw_token_absent = all(token not in raw_text for token in (alice_token, carol_token, expired_token, wrong_audience_token))
    irreversible_truthful = (
        irreversible.status == "irreversible"
        and any(event["event"] == "undo_manual_required" for event in journal.events)
        and not irreversible.compensation_trace_id
    )

    checks = {
        "identity_denied_executor_count": denied_executor_count,
        "identity_negative_cases_all_denied": all(not item["allowed"] for item in negative_results.values()),
        "valid_identity_action_executed": action_outcome.result.allowed and target_after != target_before,
        "state_restored": target_restored,
        "self_approval_denied": self_approval_denied,
        "compensation_trace_distinct": bool(effect.compensation_trace_id)
        and effect.compensation_trace_id != effect.trace_id,
        "audit_chain_ok": audit_chain_ok,
        "ledger_chain_ok": ledger_chain_ok,
        "raw_token_absent": raw_token_absent,
        "irreversible_truthful": irreversible_truthful,
    }
    go = (
        checks["identity_denied_executor_count"] == 0
        and all(value is True for key, value in checks.items() if key != "identity_denied_executor_count")
    )
    conclusion = "GO" if go else "NO-GO"
    summary = {
        "schema_version": "xa-guard-identity-undo-feasibility/v0.1",
        "conclusion": conclusion,
        "checks": checks,
        "negative_identity_cases": negative_results,
        "traces": {
            "original_action": effect.trace_id,
            "compensation": effect.compensation_trace_id,
            "irreversible_action": irreversible.trace_id,
        },
        "effects": [asdict(effect), asdict(irreversible)],
        "counts": {
            "executor_calls": runtime.executor_calls,
            "audit_records": len(_read_jsonl(audit_path)),
            "ledger_entries": len(runtime.ledger.entries),
            "effect_events": len(journal.events),
        },
        "audit_bad_line": audit_bad_line,
        "public_key_sha256": authority.public_key_sha256,
        "limitations": [
            "in-memory experiment issuer; not OIDC, JWKS discovery, or MCP transport authentication",
            "in-memory recovery material; not encrypted durable storage or restart recovery",
            "single reversible OAR object; not a generic business-system undo guarantee",
            "single-process execution; no concurrency or distributed transaction proof",
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
        "python open-agent-range/experiments/agent_identity_undo/vertical_slice.py "
        "--out docs/evidence/agent-identity-undo-spike-2026-07-12\n",
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        "# Agent Identity + Undo feasibility evidence\n\n"
        f"Conclusion: **{conclusion}**\n\n"
        "This package proves an isolated vertical slice through the real XA-Guard Pipeline, "
        "GovernanceEnforcer and Gate6, with OAR World/ToolSurface/Ledger as the synthetic downstream.\n\n"
        "It does not prove production IAM, OAuth/JWKS transport integration, durable encrypted recovery, "
        "concurrent compensation, or universal undo. No private key or compact JWS is persisted.\n",
        encoding="utf-8",
    )
    manifest = _write_manifest(output_dir)
    summary["artifact_count"] = len(manifest)
    return summary


def run_experiment(output_dir: str | Path) -> dict[str, Any]:
    """Run the complete feasibility experiment and return its summary."""

    return asyncio.run(_run(Path(output_dir).resolve()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="new evidence directory; must not already exist")
    args = parser.parse_args(argv)
    summary = run_experiment(args.out)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["conclusion"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
