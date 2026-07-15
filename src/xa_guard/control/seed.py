"""Idempotent reference assignments; user IDs are fixed in the generated realm."""

from __future__ import annotations

import asyncio

from xa_guard.control.runtime import build_runtime


REFERENCE_ASSIGNMENTS = (
    (
        "asg-reference-engineering",
        "group",
        "engineering-team",
        "general-office-agent",
        ["business_submit_ticket"],
        ["engineering_docs"],
    ),
    (
        "asg-reference-approvers",
        "group",
        "security-approvers",
        "general-office-agent",
        ["business_cancel_ticket"],
        ["engineering_docs"],
    ),
    (
        "asg-reference-admins",
        "group",
        "governance-admins",
        "general-office-agent",
        ["business_submit_ticket", "business_cancel_ticket"],
        ["engineering_docs"],
    ),
    ("asg-reference-beta-ops", "group", "beta-ops", "beta-ops-agent", ["echo"], ["beta_ops_notes"]),
)


async def seed() -> None:
    runtime = build_runtime()
    await runtime.store.connect()
    try:
        for assignment_id, subject_type, subject_id, agent_id, tools, domains in REFERENCE_ASSIGNMENTS:
            tenant_id = "beta-corp" if agent_id == "beta-ops-agent" else "acme-corp"
            runtime.service.ceiling.validate_assignment(
                tenant_id,
                {
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "agent_id": agent_id,
                    "tools": tools,
                    "data_domains": domains,
                },
            )
            await runtime.store.pool.execute(
                """
                INSERT INTO xa_assignments(assignment_id,tenant_id,subject_type,subject_id,agent_id,tools,
                  data_domains,changed_by)
                VALUES($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,'reference-bootstrap')
                ON CONFLICT (assignment_id) DO NOTHING
                """,
                assignment_id,
                tenant_id,
                subject_type,
                subject_id,
                agent_id,
                tools,
                domains,
            )
    finally:
        await runtime.store.close()


if __name__ == "__main__":
    asyncio.run(seed())
