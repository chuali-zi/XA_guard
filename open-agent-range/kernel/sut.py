"""SUT — 被测防护契约。

契约见 ``docs/architecture/kernel-architecture.md`` §6 与 ``docs/architecture/decoupling-contract.md`` §2。
SUT 拿到工具调用尝试，返回 allow / deny / proxy 决策并产出审计。XA-Guard 只是"guard 模式"下的一个 SUT。

本模块状态：
- SUT 契约 + NullSUT（直通基线）：**已实现**。
- GuardStubSUT（确定性替身，防判据虚假加固）：**已实现**。
- XaGuardSUT（外部 XA-Guard，经 MCP/CLI 接入）：**配置生成 + 离线策略 stub 已实现**；
  真实 MCP subprocess 串接待 SP5 live 授权后补齐。

红线（decoupling-contract）：内核**不 import xa_guard、不改其策略**；只按场景/席位生成临时
Gate3/Gate4 配置喂给外部进程，读其落盘审计当证据。
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import sys
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kernel.policy_overlay import PolicyOverlay, overlay_from_scenario, write_gate3_policy


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]


@dataclass
class AuditRecord:
    tool: str
    decision: str  # allow / deny / proxy
    reason: str


@dataclass(frozen=True)
class XaGuardArtifacts:
    """一次 attempt 生成的临时 SUT 配置路径（证据工件）。"""

    xa_guard_yaml: Path
    gate3_rules: Path
    gate4_capabilities: Path
    audit_dir: Path
    pending_path: Path
    tool_schemas: Path


class SUT:
    """被测防护统一边界。子类只需实现 decide()。"""

    sut_id: str = "sut"

    def __init__(self) -> None:
        self.audit: list[AuditRecord] = []

    def decide(self, principal: str, call: ToolCall) -> tuple[str, str]:
        raise NotImplementedError

    def begin_attempt(self) -> None:
        """Optional lifecycle hook for SUTs that keep per-attempt resources."""

    def end_attempt(self) -> None:
        """Optional lifecycle hook for SUTs that keep per-attempt resources."""

    def invoke(self, world: Any, ledger: Any, principal: str, call: ToolCall, surface: Any) -> dict[str, Any]:
        """裁决 -> 记审计/账本 -> 放行则经工具面执行（工具负责改世界 + 副作用落账）。"""
        decision, reason = self.decide(principal, call)
        self.audit.append(AuditRecord(tool=call.tool, decision=decision, reason=reason))
        _append_tool_attempt(world, ledger, principal, call)
        _append_sut_decision(world, ledger, principal, call, decision=decision, reason=reason)
        if decision == "deny":
            return {"decision": "deny", "reason": reason, "executed": False}
        output = surface.execute(call.tool, world, ledger, principal, dict(call.args))
        output.setdefault("decision", "allow")
        output.setdefault("executed", True)
        return output


class NullSUT(SUT):
    """直通基线：什么都放行。用于测 ASR_null（裸奔 agent）。"""

    sut_id = "null-passthrough"

    def decide(self, principal: str, call: ToolCall) -> tuple[str, str]:
        return "allow", "null passthrough executes everything"

    def invoke(self, world: Any, ledger: Any, principal: str, call: ToolCall, surface: Any) -> dict[str, Any]:
        """Naked baseline stays noise-free: only actual tool side effects enter the ledger."""
        decision, reason = self.decide(principal, call)
        self.audit.append(AuditRecord(tool=call.tool, decision=decision, reason=reason))
        output = surface.execute(call.tool, world, ledger, principal, dict(call.args))
        output.setdefault("decision", "allow")
        output.setdefault("executed", True)
        return output


class GuardStubSUT(SUT):
    """确定性策略替身：拦截"携带敏感标记的外部外发"。

    存在的意义是让判据/流程在没有真实 XA-Guard 时也能测 A/B，且**不预置在 mock 工具里**
    （否则 Null 基线会被虚假加固，见 decoupling-contract §3）。
    """

    sut_id = "guard-stub"

    def __init__(
        self,
        sensitive_markers: tuple[str, ...] = (),
        deny_external_tools: tuple[str, ...] = ("send_email", "send"),
    ) -> None:
        super().__init__()
        self.sensitive_markers = tuple(m.lower() for m in sensitive_markers)
        self.deny_external_tools = deny_external_tools

    def decide(self, principal: str, call: ToolCall) -> tuple[str, str]:
        if call.tool in self.deny_external_tools:
            body = str(call.args.get("body", "")) + " " + str(call.args.get("content", ""))
            to = str(call.args.get("to", ""))
            body_l = body.lower()
            hit = any(marker in body_l for marker in self.sensitive_markers)
            if hit and to:
                return "deny", "external egress of sensitive-marked content blocked"
        return "allow", "no policy violation"


def path_text(path: Path) -> str:
    return str(path.resolve())


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(yaml_string(value) for value in values) + "]"


def find_xa_guard_root(start: Path | None = None) -> Path:
    """定位含 ``src/xa_guard/server.py`` 的 XA-Guard 根目录（外部仓库，不 import）。"""
    anchor = (start or Path.cwd()).resolve()
    candidates = [anchor, *anchor.parents]
    for candidate in candidates:
        if (candidate / "src/xa_guard/server.py").exists():
            return candidate
    sibling = anchor.parent
    if (sibling / "src/xa_guard/server.py").exists():
        return sibling
    raise FileNotFoundError("could not locate xa_guard root containing src/xa_guard/server.py")


def write_xa_guard_config(
    *,
    path: Path,
    xa_guard_root: Path,
    downstream_command: list[str],
    audit_dir: Path,
    pending_path: Path,
    tool_capabilities_file: Path,
    policy_file: Path,
) -> None:
    """生成喂给 ``python -m xa_guard.server --config`` 的临时 yaml（证据，非源码）。"""
    root = xa_guard_root.resolve()
    text = f"""xa_guard:
  upstream:
    transport: stdio

  downstream:
    - name: range_target
      command: {yaml_list(downstream_command)}
      transport: stdio
      env_passthrough: [PYTHONPATH, PYTHONIOENCODING]

  gates:
    gate1:
      enabled: true
      detectors:
        - name: rule
          type: rule
          enabled: true
          patterns_file: {yaml_string(path_text(root / "policies/baseline/gate1_input_patterns.yaml"))}
      patterns_file: {yaml_string(path_text(root / "policies/baseline/gate1_input_patterns.yaml"))}
    gate2:
      enabled: true
      hitl_required_for: [red]
      elicitation_fallback: deny
      tool_risk_file: {yaml_string(path_text(root / "policies/baseline/gate2_tool_risks.yaml"))}
      prefer_layered: false
    gate3:
      enabled: true
      backend: python
      policy_file: {yaml_string(path_text(policy_file))}
      prefer_layered: false
    gate4:
      enabled: true
      strict_mode: false
      tool_capabilities_file: {yaml_string(path_text(tool_capabilities_file))}
      prefer_layered: false
    gate5:
      enabled: false
    gate6:
      enabled: true
      audit_dir: {yaml_string(path_text(audit_dir))}
      hash_algo: sha256
    policy_layered:
      enabled: false

  pending_approvals_path: {yaml_string(path_text(pending_path))}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_sut_evidence_configs(
    store: Any,
    *,
    scenario: Any,
    surface: Any,
    xa_guard_root: Path,
    downstream_command: list[str],
    policy: PolicyOverlay | None = None,
) -> XaGuardArtifacts:
    """把 Gate3/Gate4/xa-guard.yaml 写入 EvidenceStore（证据包标准工件名）。"""
    overlay = policy or overlay_from_scenario(scenario)
    root = xa_guard_root.resolve()
    baseline_gate3 = root / "policies/baseline/gate3_rules.yaml"
    gate3_path = store.path("gate3-rules.yaml")
    gate4_path = store.path("gate4-capabilities.yaml")
    schemas_path = store.path("mcp-tool-schemas.json")
    xa_path = store.path("xa-guard.yaml")
    audit_dir = store.path("xa-guard-audit")
    pending_path = store.path("pending-approvals.jsonl")
    audit_dir.mkdir(parents=True, exist_ok=True)

    write_gate3_policy(gate3_path, baseline_gate3, overlay)
    gate4_path.write_text(surface.gate4_capability_document(), encoding="utf-8", newline="\n")
    schemas_path.write_text(
        json.dumps(surface.mcp_tool_schemas(), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    if not downstream_command:
        downstream_command = [
            sys.executable,
            "-m",
            "kernel.mcp_echo_server",
            "--tools",
            path_text(schemas_path),
        ]
    write_xa_guard_config(
        path=xa_path,
        xa_guard_root=root,
        downstream_command=downstream_command,
        audit_dir=audit_dir,
        pending_path=pending_path,
        tool_capabilities_file=gate4_path,
        policy_file=gate3_path,
    )
    return XaGuardArtifacts(
        xa_guard_yaml=xa_path,
        gate3_rules=gate3_path,
        gate4_capabilities=gate4_path,
        audit_dir=audit_dir,
        pending_path=pending_path,
        tool_schemas=schemas_path,
    )


class _XaGuardLiveSession:
    """A persistent MCP stdio session used for all ToolCalls in one attempt."""

    def __init__(self, *, command: list[str], env: dict[str, str], timeout_s: float = 60.0) -> None:
        self.command = list(command)
        self.env = dict(env)
        self.timeout_s = timeout_s
        self._ready: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
        self._requests: queue.Queue[Any] = queue.Queue()
        self._thread = threading.Thread(target=self._thread_main, name="xa-guard-live-session", daemon=True)

    def start(self) -> None:
        self._thread.start()
        status, payload = self._ready.get(timeout=self.timeout_s)
        if status != "ok":
            if isinstance(payload, BaseException):
                raise RuntimeError("failed to start XA-Guard live session") from payload
            raise RuntimeError(f"failed to start XA-Guard live session: {payload}")

    def call_tool(self, tool: str, arguments: dict[str, Any]) -> str:
        response: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
        self._requests.put((tool, dict(arguments), response))
        status, payload = response.get(timeout=self.timeout_s)
        if status != "ok":
            if isinstance(payload, BaseException):
                raise RuntimeError("XA-Guard live session tool call failed") from payload
            raise RuntimeError(f"XA-Guard live session tool call failed: {payload}")
        return str(payload)

    def close(self) -> None:
        self._requests.put(None)
        self._thread.join(timeout=10.0)

    def _thread_main(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        try:
            from mcp import ClientSession
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except Exception as exc:  # pragma: no cover
            self._ready.put(("error", exc))
            return

        params = StdioServerParameters(
            command=self.command[0],
            args=self.command[1:],
            env=self.env,
        )
        try:
            async with AsyncExitStack() as stack:
                read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await session.initialize()
                self._ready.put(("ok", None))
                loop = asyncio.get_running_loop()
                while True:
                    request = await loop.run_in_executor(None, self._requests.get)
                    if request is None:
                        return
                    tool, arguments, response = request
                    try:
                        result = await session.call_tool(tool, arguments)
                        response.put(("ok", _mcp_result_text(result)))
                    except BaseException as exc:  # pragma: no cover - exercised by live infra failures
                        response.put(("error", exc))
        except BaseException as exc:  # pragma: no cover - exercised by live infra failures
            self._ready.put(("error", exc))


class XaGuardSUT(SUT):
    """外部 XA-Guard（guard 模式）经 MCP stdio / CLI 接入。

    离线模式：按 PolicyOverlay 做确定性 gate3 风格裁决（与 GuardStubSUT 同形，参数来自场景）。
    Live 模式：生成配置并通过真实 ``xa_guard.server`` stdio MCP 审查每次工具调用；
    allow 后由 range 本进程执行 ToolSurface，deny 则不产生世界副作用。
    """

    sut_id = "xa-guard"

    def __init__(
        self,
        *,
        policy: PolicyOverlay | None = None,
        xa_guard_root: Path | None = None,
        downstream_command: list[str] | None = None,
        live: bool = False,
    ) -> None:
        super().__init__()
        self.policy = policy
        self.xa_guard_root = xa_guard_root
        self.downstream_command = list(downstream_command or [])
        self.live = live
        self.artifacts: XaGuardArtifacts | None = None
        self._xa_guard_root_resolved: Path | None = None
        self._live_session: _XaGuardLiveSession | None = None
        self._session_generation = 0
        self._live_session_summary: dict[str, Any] | None = None

    def prepare(self, store: Any, scenario: Any, surface: Any) -> XaGuardArtifacts:
        return self.write_configs(store, scenario, surface)

    def write_configs(self, store: Any, scenario: Any, surface: Any) -> XaGuardArtifacts:
        root = self.xa_guard_root or find_xa_guard_root()
        self._xa_guard_root_resolved = root.resolve()
        self.artifacts = write_sut_evidence_configs(
            store,
            scenario=scenario,
            surface=surface,
            xa_guard_root=root,
            downstream_command=self.downstream_command,
            policy=self.policy,
        )
        return self.artifacts

    def server_command(self) -> list[str]:
        if self.artifacts is None:
            raise RuntimeError("call write_configs() before server_command()")
        return [
            sys.executable,
            "-m",
            "xa_guard.server",
            "--config",
            path_text(self.artifacts.xa_guard_yaml),
        ]

    def decide(self, principal: str, call: ToolCall) -> tuple[str, str]:
        if self.live:
            raise RuntimeError("XaGuardSUT live decisions require invoke(), not decide()")
        return self._offline_gate3_decide(call)

    def begin_attempt(self) -> None:
        if not self.live:
            return
        if self.artifacts is None:
            raise RuntimeError("call prepare()/write_configs() before begin_attempt()")
        if self._live_session is not None:
            return
        self._session_generation += 1
        session_id = f"xa-guard-live-session-{self._session_generation:03d}"
        self._live_session_summary = {
            "sut_id": self.sut_id,
            "live": True,
            "session_scope": "attempt",
            "session_id": session_id,
            "server_command": self.server_command(),
            "audit_dir": path_text(self.artifacts.audit_dir),
            "started": False,
            "closed": False,
            "process_start_count": 0,
            "tool_call_count": 0,
            "tools": [],
            "errors": [],
        }
        session = _XaGuardLiveSession(command=self.server_command(), env=self._child_env())
        try:
            session.start()
        except BaseException as exc:
            self._live_session_summary["errors"].append({"type": type(exc).__name__, "message": str(exc)})
            raise
        self._live_session = session
        self._live_session_summary["started"] = True
        self._live_session_summary["process_start_count"] = 1

    def end_attempt(self) -> None:
        if self._live_session is None:
            return
        try:
            self._live_session.close()
            if self._live_session_summary is not None:
                self._live_session_summary["closed"] = True
        finally:
            self._live_session = None

    def live_session_summary(self) -> dict[str, Any] | None:
        if self._live_session_summary is None:
            return None
        return dict(self._live_session_summary)

    def invoke(self, world: Any, ledger: Any, principal: str, call: ToolCall, surface: Any) -> dict[str, Any]:
        if not self.live:
            return super().invoke(world, ledger, principal, call, surface)
        decision, reason = self._live_decide(principal, call)
        self.audit.append(AuditRecord(tool=call.tool, decision=decision, reason=reason))
        _append_tool_attempt(world, ledger, principal, call)
        _append_sut_decision(world, ledger, principal, call, decision=decision, reason=reason)
        if decision == "deny":
            return {"decision": "deny", "reason": reason, "executed": False}
        output = surface.execute(call.tool, world, ledger, principal, dict(call.args))
        output.setdefault("decision", "allow")
        output.setdefault("executed", True)
        return output

    def _live_decide(self, principal: str, call: ToolCall) -> tuple[str, str]:
        if self.artifacts is None:
            raise RuntimeError("call prepare()/write_configs() before using XaGuardSUT(live=True)")
        before = _audit_row_count(self.artifacts.audit_dir)
        result_text = self._call_xa_guard(call, principal=principal)
        row = _latest_audit_row(self.artifacts.audit_dir, after=before)
        if row:
            decision = str(row.get("gen_ai.decision.final") or "allow")
            reason = str(row.get("gen_ai.decision.final_reason") or "")
            if decision in {"deny", "require_approval"}:
                return "deny", reason or "xa-guard live denied tool call"
            return "allow", reason or "xa-guard live allowed tool call"
        if "XA-Guard 已拦截" in result_text or "XA-Guard 等待人工审批" in result_text:
            return "deny", result_text
        return "allow", result_text or "xa-guard live allowed tool call"

    def _call_xa_guard(self, call: ToolCall, *, principal: str) -> str:
        arguments = self._call_arguments(call, principal=principal)
        if self._live_session is not None:
            result = self._live_session.call_tool(call.tool, arguments)
            self._record_live_session_call(call, principal=principal)
            return result
        result = asyncio.run(self._call_xa_guard_once(call, arguments))
        self._record_live_session_call(call, principal=principal, fallback_per_call=True)
        return result

    async def _call_xa_guard_once(self, call: ToolCall, arguments: dict[str, Any]) -> str:
        try:
            from mcp import ClientSession
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("XaGuardSUT live mode requires the mcp Python package") from exc

        command = self.server_command()
        params = StdioServerParameters(
            command=command[0],
            args=command[1:],
            env=self._child_env(),
        )
        async with AsyncExitStack() as stack:
            read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            result = await session.call_tool(call.tool, arguments)
        return _mcp_result_text(result)

    def _call_arguments(self, call: ToolCall, *, principal: str) -> dict[str, Any]:
        arguments = dict(call.args)
        envelope = arguments.setdefault("_xa_guard", {})
        if isinstance(envelope, dict):
            envelope.setdefault("human_principal", principal)
            envelope.setdefault("agent_id", "open-agent-range")
        return arguments

    def _record_live_session_call(
        self,
        call: ToolCall,
        *,
        principal: str,
        fallback_per_call: bool = False,
    ) -> None:
        if self._live_session_summary is None:
            self._live_session_summary = {
                "sut_id": self.sut_id,
                "live": True,
                "session_scope": "per_call_fallback",
                "session_id": "xa-guard-live-per-call",
                "started": False,
                "closed": True,
                "process_start_count": 0,
                "tool_call_count": 0,
                "tools": [],
                "errors": [],
            }
        self._live_session_summary["tool_call_count"] = int(self._live_session_summary.get("tool_call_count", 0)) + 1
        if fallback_per_call:
            self._live_session_summary["session_scope"] = "per_call_fallback"
            self._live_session_summary["process_start_count"] = int(
                self._live_session_summary.get("process_start_count", 0)
            ) + 1
        self._live_session_summary.setdefault("tools", []).append({"principal": principal, "tool": call.tool})

    def _child_env(self) -> dict[str, str]:
        env = dict(os.environ)
        root = self._xa_guard_root_resolved or self.xa_guard_root or find_xa_guard_root()
        range_root = Path(__file__).resolve().parents[1]
        parts = [
            str((root / "src").resolve()),
            str(root.resolve()),
            str(range_root.resolve()),
            str(Path.cwd().resolve()),
        ]
        existing = env.get("PYTHONPATH")
        if existing:
            parts.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(parts)
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _offline_gate3_decide(self, call: ToolCall) -> tuple[str, str]:
        policy = self.policy or PolicyOverlay(scenario_id="scenario")
        tools = policy.deny_external_tools or ("send_email", "send", "send_message")
        if call.tool not in tools:
            return "allow", "tool not in gate3 triggers"
        markers = tuple(m.lower() for m in policy.sensitive_markers)
        if not markers:
            return "allow", "no sensitive markers configured for scenario"
        body = str(call.args.get("body", "")) + " " + str(call.args.get("content", ""))
        to = str(call.args.get("to", ""))
        body_l = body.lower()
        hit = any(marker.lower() in body_l for marker in markers)
        if hit and to:
            return "deny", "gate3 overlay: sensitive-marked external egress blocked"
        return "allow", "gate3 overlay: no marker match"


def _append_tool_attempt(world: Any, ledger: Any, principal: str, call: ToolCall) -> None:
    ledger.append(
        actor=principal,
        principal=principal,
        seat=principal,
        role=_role(world, principal),
        action="tool_attempt",
        tool=call.tool,
        data_ref=_data_ref_from_call(call),
        classification="PUBLIC",
        decision="attempted",
        ts=_current_ts(world),
        **_ledger_chains(call),
    )


def _append_sut_decision(
    world: Any,
    ledger: Any,
    principal: str,
    call: ToolCall,
    *,
    decision: str,
    reason: str,
) -> None:
    ledger.append(
        actor=self_actor(world),
        principal=principal,
        seat=principal,
        role=_role(world, principal),
        action="sut_decision",
        tool=call.tool,
        data_ref=_decision_ref(call, reason),
        classification="PUBLIC",
        decision=decision,
        ts=_current_ts(world),
        **_ledger_chains(call),
    )


def self_actor(world: Any) -> str:
    return str(world.domain_state.get("sut_actor", "SUT")) if hasattr(world, "domain_state") else "SUT"


def _role(world: Any, principal: str) -> str:
    p = getattr(world, "principals", {}).get(principal) if hasattr(world, "principals") else None
    return getattr(p, "role", "") if p else ""


def _current_ts(world: Any) -> int:
    state = getattr(world, "domain_state", {})
    clock = state.get("clock", {}) if isinstance(state, dict) else {}
    if isinstance(clock, dict):
        return int(clock.get("current_ts", 0) or 0)
    return 0


def _ledger_chains(call: ToolCall) -> dict[str, Any]:
    chains: dict[str, Any] = {}
    for key in ("identity_chain", "authorization_chain", "delegation_chain"):
        value = call.args.get(key)
        if isinstance(value, list):
            chains[key] = value
    return chains


def _data_ref_from_call(call: ToolCall) -> str | None:
    for key in (
        "data_ref",
        "record_id",
        "report_id",
        "repo",
        "artifact",
        "build_id",
        "service",
        "ticket_id",
        "approval_ticket",
        "package_id",
        "seat_id",
        "locator",
    ):
        value = call.args.get(key)
        if value not in (None, ""):
            return str(value)
    sources = call.args.get("sources")
    if isinstance(sources, list) and sources:
        return str(sources[0])
    return None


def _decision_ref(call: ToolCall, reason: str) -> str:
    # Keep full prompt/tool arguments out of the ledger; store a stable non-secret reference.
    ref = _data_ref_from_call(call)
    if ref:
        return ref
    return reason[:96] if reason else call.tool


def _mcp_result_text(result: Any) -> str:
    blocks = getattr(result, "content", None) or []
    texts: list[str] = []
    for block in blocks:
        text = getattr(block, "text", None)
        if text is not None:
            texts.append(str(text))
        else:
            texts.append(str(block))
    return "\n".join(texts)


def _audit_rows(audit_dir: Path) -> list[dict[str, Any]]:
    path = audit_dir / "audit.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _audit_row_count(audit_dir: Path) -> int:
    return len(_audit_rows(audit_dir))


def _latest_audit_row(audit_dir: Path, *, after: int) -> dict[str, Any] | None:
    rows = _audit_rows(audit_dir)
    if len(rows) <= after:
        return rows[-1] if rows else None
    return rows[-1]
