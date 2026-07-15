"""Create one real approved effect for the Kind Worker-takeover exercise.

The caller is responsible for port-forwarding the in-cluster API and arming
the reference business fault immediately before approval. Tokens remain in
memory and this module returns only public effect/request identifiers.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from reference_acceptance_lib import AcceptanceFailure, ReferenceIdentity  # noqa: E402


def _object(response: httpx.Response, status: int, label: str) -> dict[str, Any]:
    if response.status_code != status:
        raise AcceptanceFailure(f"{label} failed with HTTP {response.status_code}")
    try:
        value = response.json()
    except ValueError as exc:
        raise AcceptanceFailure(f"{label} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise AcceptanceFailure(f"{label} returned a non-object response")
    return value


def prepare_takeover(
    *,
    base_url: str,
    issuer: str,
    before_approve: Callable[[], None],
) -> dict[str, str]:
    """Create, request, and independently approve one delayed compensation."""

    identity = ReferenceIdentity(issuer=issuer, control_url=base_url)
    alice = identity.agent_token("alice")
    dora = identity.agent_token("dora")
    with httpx.Client(timeout=20) as client:
        created = _object(
            client.post(
                base_url.rstrip("/") + "/control/v1/tickets",
                headers=identity.headers(alice),
                json={
                    "title": "Kind Worker lease takeover acceptance",
                    "description": "A real delayed compensation used to prove replica takeover.",
                    "priority": "high",
                    "data_domain": "engineering_docs",
                },
            ),
            201,
            "takeover ticket creation",
        )
        effect_id = str(created.get("effect_id") or "")
        if not effect_id.startswith("eff-"):
            raise AcceptanceFailure("takeover ticket returned no effect identifier")
        requested = _object(
            client.post(
                base_url.rstrip("/") + f"/control/v1/effects/{effect_id}/undo-requests",
                headers=identity.headers(alice, idempotency_key=f"kind-takeover-{effect_id}"),
                json={"reason": "Kind HA takeover acceptance"},
            ),
            201,
            "takeover Undo request",
        )
        request_id = str(requested.get("request_id") or "")
        if not request_id.startswith("undo-"):
            raise AcceptanceFailure("takeover request returned no request identifier")
        before_approve()
        _object(
            client.post(
                base_url.rstrip("/") + f"/control/v1/undo-requests/{request_id}/decision",
                headers=identity.headers(dora),
                json={
                    "decision": "approve",
                    "reason": "Independent Kind HA takeover approval",
                },
            ),
            200,
            "takeover approval",
        )
    return {"effect_id": effect_id, "request_id": request_id}
