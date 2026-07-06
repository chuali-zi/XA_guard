"""Ledger — 不可篡改地面真值账本（内核脊梁）。

契约见 ``docs/architecture/ledger-schema.md``。
账本是安全判据的唯一真相源，也是追责证据。每一次世界副作用与关键决策都 append 成一条
不可篡改（hash chain）、可重放、可追责（身份/授权/委托三链）的事实。

本模块状态：
- hash chain（append / _hash / verify_hash_chain）：**已移植自 spike，可用**。
- 三链字段（identity/authorization/delegation）：schema 已就位，**链的语义校验待补**（见 TODO）。
- JSONL 持久化：write / load 已实现。
- 重放取证：见 replay() 的 TODO(SP5)。

铁律：账本只如实记事实，**不判断攻击、不分类攻击、不反推 SUT 策略**；不落机密明文，只存 data_ref + 分级。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any


@dataclass
class LedgerEntry:
    """一条账本事实，字段对齐 ledger-schema.md §2。"""

    seq: int
    actor: str
    principal: str
    seat: str
    role: str
    action: str
    tool: str
    data_ref: str | None
    classification: str
    to: str | None
    external: bool
    decision: str
    ts: int = 0  # 业务逻辑时钟（世界 tick），非墙钟
    identity_chain: list[dict[str, Any]] = field(default_factory=list)
    authorization_chain: list[dict[str, Any]] = field(default_factory=list)
    delegation_chain: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    prev_hash: str | None = None
    hash: str = ""

    def hashable(self) -> dict[str, Any]:
        """规范化视图：除 hash 外的全部字段，用于计算本条 hash。"""
        data = {k: v for k, v in self.__dict__.items() if k != "hash"}
        return data

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class Ledger:
    """append-only 账本。内存态 + 可选 JSONL 落盘。"""

    def __init__(self, path: Path | str | None = None) -> None:
        self.entries: list[LedgerEntry] = []
        # 落盘路径；给定时每次 append 追加一行 JSONL（append-only，落盘即成证据）。
        self.path: Path | None = Path(path) if path else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        *,
        actor: str,
        principal: str,
        role: str,
        action: str,
        tool: str = "",
        seat: str = "",
        data_ref: str | None = None,
        classification: str = "PUBLIC",
        to: str | None = None,
        external: bool = False,
        decision: str = "null",
        ts: int = 0,
        identity_chain: list[dict[str, Any]] | None = None,
        authorization_chain: list[dict[str, Any]] | None = None,
        delegation_chain: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LedgerEntry:
        entry = LedgerEntry(
            seq=len(self.entries) + 1,
            actor=actor,
            principal=principal,
            seat=seat,
            role=role,
            action=action,
            tool=tool,
            data_ref=data_ref,
            classification=classification,
            to=to,
            external=external,
            decision=decision,
            ts=ts,
            identity_chain=identity_chain or [],
            authorization_chain=authorization_chain or [],
            delegation_chain=delegation_chain or [],
            metadata=metadata or {},
            prev_hash=self.entries[-1].hash if self.entries else None,
        )
        entry.hash = self._hash(entry.hashable())
        self.entries.append(entry)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(entry.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return entry

    @staticmethod
    def _hash(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()

    def verify_hash_chain(self) -> bool:
        """逐条重算 hash 并核对 prev_hash 衔接；任一处不符即判定篡改（AT10）。"""
        previous_hash: str | None = None
        for entry in self.entries:
            if entry.prev_hash != previous_hash:
                return False
            if self._hash(entry.hashable()) != entry.hash:
                return False
            previous_hash = entry.hash
        return True

    # --- 持久化 / 重放 -----------------------------------------------------------

    @classmethod
    def load(cls, path: Path | str) -> "Ledger":
        """从 append-only JSONL 载入。用于取证与回归对照。"""
        ledger = cls()
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            entry = LedgerEntry(**raw)
            ledger.entries.append(entry)
        return ledger

    def replay(self, world: Any) -> Any:
        """按 seq 顺序重演，复现世界终态与判据结果（ledger-schema.md §6）。

        当前实现是 SP7 的第一层 deterministic replay projection：只从 ledger 事实重建
        可审计投影（egress、SUT attempt/decision、关键队列/状态索引），不读取原始
        prompt 或机密明文。对历史 entry 中未落入账本的工具入参细节（如 CI status）
        会如实标记为 limitation，而不是伪造完整世界。
        """
        projection: dict[str, Any] = {
            "deterministic_world_replay": "ledger_projection_v1",
            "entry_count": len(self.entries),
            "hash_chain_ok": self.verify_hash_chain(),
            "last_hash": self.entries[-1].hash if self.entries else "",
            "actions": {},
            "egress": [],
            "tool_attempts": [],
            "sut_decisions": [],
            "queues": {"ticket": {}, "approval": {}, "ci": {}, "audit": {}},
            "services": {},
            "plugins": {},
            "registry": {},
            "payments": {},
            "dynamic_tools": [],
            "limitations": [],
        }
        for entry in self.entries:
            projection["actions"][entry.action] = projection["actions"].get(entry.action, 0) + 1
            replay = entry.metadata.get("replay", {}) if isinstance(entry.metadata, dict) else {}
            if isinstance(replay, dict):
                _apply_replay_metadata(projection, replay)
            if entry.action in {"send", "send_email"}:
                projection["egress"].append(
                    {
                        "seq": entry.seq,
                        "ts": entry.ts,
                        "actor": entry.actor,
                        "tool": entry.tool,
                        "data_ref": entry.data_ref,
                        "classification": entry.classification,
                        "to": entry.to,
                        "external": entry.external,
                    }
                )
            elif entry.action == "tool_attempt":
                projection["tool_attempts"].append(_entry_ref(entry))
            elif entry.action == "sut_decision":
                item = _entry_ref(entry)
                item["decision"] = entry.decision
                projection["sut_decisions"].append(item)
            elif entry.action == "submit_ticket":
                if _has_replay_item(replay):
                    continue
                if entry.data_ref:
                    projection["queues"]["ticket"][entry.data_ref] = {
                        "id": entry.data_ref,
                        "status": "submitted",
                        "owner": entry.actor,
                        "updated_ts": entry.ts,
                    }
            elif entry.action == "request_approval":
                if _has_replay_item(replay):
                    continue
                if entry.data_ref:
                    projection["queues"]["approval"][entry.data_ref] = {
                        "id": entry.data_ref,
                        "approval_ticket": entry.data_ref,
                        "status": "pending",
                        "requester": entry.actor,
                        "updated_ts": entry.ts,
                    }
            elif entry.action == "approve":
                if _has_replay_item(replay):
                    continue
                key = entry.data_ref or f"approval-{entry.seq}"
                projection["queues"]["approval"][key] = {
                    "id": key,
                    "target": entry.data_ref,
                    "status": "approved" if entry.decision in {"allow", "null"} else entry.decision,
                    "approver": entry.actor,
                    "updated_ts": entry.ts,
                }
            elif entry.action == "restart_service":
                if isinstance(replay, dict) and replay.get("service"):
                    continue
                service = entry.data_ref or "service"
                projection["services"][service] = {
                    "service": service,
                    "status": "changed",
                    "actor": entry.actor,
                    "updated_ts": entry.ts,
                }
            elif entry.action == "manage_ci":
                if _has_replay_item(replay):
                    continue
                build_id = entry.data_ref or f"build-{entry.seq}"
                item = projection["queues"]["ci"].setdefault(
                    build_id,
                    {"id": build_id, "build_id": build_id, "events": []},
                )
                item["events"].append({"seq": entry.seq, "actor": entry.actor, "ts": entry.ts})
            elif entry.action == "publish_plugin":
                if isinstance(replay, dict) and replay.get("plugin"):
                    continue
                if entry.data_ref:
                    projection["plugins"][entry.data_ref] = {
                        "plugin": entry.data_ref,
                        "publisher": entry.actor,
                        "updated_ts": entry.ts,
                    }
            elif entry.action == "update_registry":
                if isinstance(replay, dict) and replay.get("registry"):
                    continue
                if entry.data_ref:
                    projection["registry"][entry.data_ref] = {
                        "seat_id": entry.data_ref,
                        "actor": entry.actor,
                        "updated_ts": entry.ts,
                    }
            elif entry.action == "export_evidence":
                if _has_replay_item(replay):
                    continue
                if entry.data_ref:
                    projection["queues"]["audit"][entry.data_ref] = {
                        "id": entry.data_ref,
                        "package_id": entry.data_ref,
                        "status": "exported",
                        "actor": entry.actor,
                        "updated_ts": entry.ts,
                    }
            elif entry.action == "dynamic_tool_call":
                projection["dynamic_tools"].append(_entry_ref(entry))

        ci_items = projection["queues"]["ci"].values()
        if any(isinstance(item, dict) and "events" in item and "status" not in item for item in ci_items):
            projection["limitations"].append(
                "CI replay keeps per-build event order, but exact status requires tool argument/state payloads in ledger entries."
            )
        if any(isinstance(item, dict) and item.get("status") == "changed" for item in projection["services"].values()):
            projection["limitations"].append(
                "Service replay proves a service-changing action occurred; exact terminal status requires state payloads in ledger entries."
            )

        if hasattr(world, "domain_state") and isinstance(world.domain_state, dict):
            world.domain_state["ledger_replay"] = projection
        return projection


def _entry_ref(entry: LedgerEntry) -> dict[str, Any]:
    return {
        "seq": entry.seq,
        "ts": entry.ts,
        "actor": entry.actor,
        "principal": entry.principal,
        "tool": entry.tool,
        "data_ref": entry.data_ref,
        "classification": entry.classification,
    }


def _has_replay_item(replay: Any) -> bool:
    return isinstance(replay, dict) and isinstance(replay.get("item"), dict) and replay.get("queue")


def _apply_replay_metadata(projection: dict[str, Any], replay: dict[str, Any]) -> None:
    queue = replay.get("queue")
    item = replay.get("item")
    if isinstance(queue, str) and isinstance(item, dict):
        bucket = projection["queues"].setdefault(queue, {})
        key = str(
            item.get("id")
            or item.get("ticket_id")
            or item.get("approval_ticket")
            or item.get("build_id")
            or item.get("package_id")
            or f"{queue}-{len(bucket) + 1}"
        )
        bucket[key] = dict(item)
    service = replay.get("service")
    if isinstance(service, dict):
        key = str(service.get("service") or service.get("id") or f"service-{len(projection['services']) + 1}")
        projection["services"][key] = dict(service)
        ticket_id = str(replay.get("ticket_id") or "")
        if ticket_id:
            projection["queues"].setdefault("ticket", {})[ticket_id] = {
                "id": ticket_id,
                "ticket_id": ticket_id,
                "status": str(replay.get("ticket_status") or "updated"),
                "updated_ts": service.get("updated_ts", 0),
            }
    plugin = replay.get("plugin")
    state = replay.get("state")
    if plugin and isinstance(state, dict):
        projection["plugins"][str(plugin)] = {"plugin": str(plugin), **dict(state)}
    registry = replay.get("registry")
    if isinstance(registry, dict):
        key = str(registry.get("seat_id") or registry.get("principal") or f"registry-{len(projection['registry']) + 1}")
        projection["registry"][key] = dict(registry)
    payment = replay.get("payment")
    if isinstance(payment, dict):
        key = str(payment.get("payment_id") or f"payment-{len(projection['payments']) + 1}")
        projection["payments"][key] = dict(payment)
