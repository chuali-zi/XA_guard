from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.p2.base import CapabilityStatus
from enterprise_agent_range.p2.permissions import (
    SPEC,
    GrantAuthority,
    GrantRequest,
)


class PermissionsSpecTest(unittest.TestCase):
    def test_spec_is_implemented(self) -> None:
        self.assertEqual(SPEC.key, "permissions")
        self.assertEqual(SPEC.status, CapabilityStatus.IMPLEMENTED)


class IssueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = GrantAuthority()
        self.request = GrantRequest(
            principal_id="svc-agent-1",
            capability="read_orders",
            scope=("orders:read",),
            ttl_seconds=300,
            justification="synthetic range test",
        )

    def test_issue_sets_issued_at_and_expires_at(self) -> None:
        grant = self.authority.issue(self.request, now_epoch=1_000)
        self.assertEqual(grant.issued_at, 1_000)
        self.assertEqual(grant.expires_at, 1_300)
        self.assertFalse(grant.revoked)
        self.assertEqual(grant.request, self.request)

    def test_grant_id_is_deterministic_for_same_input(self) -> None:
        first = self.authority.issue(self.request, now_epoch=1_000)
        second = self.authority.issue(self.request, now_epoch=1_000)
        self.assertEqual(first.grant_id, second.grant_id)
        self.assertTrue(first.grant_id.startswith("grant-"))

    def test_grant_id_differs_when_now_epoch_differs(self) -> None:
        first = self.authority.issue(self.request, now_epoch=1_000)
        second = self.authority.issue(self.request, now_epoch=1_001)
        self.assertNotEqual(first.grant_id, second.grant_id)

    def test_grant_id_differs_when_request_differs(self) -> None:
        other_request = GrantRequest(
            principal_id="svc-agent-2",
            capability="read_orders",
            scope=("orders:read",),
            ttl_seconds=300,
        )
        first = self.authority.issue(self.request, now_epoch=1_000)
        second = self.authority.issue(other_request, now_epoch=1_000)
        self.assertNotEqual(first.grant_id, second.grant_id)


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = GrantAuthority()
        self.request = GrantRequest(
            principal_id="svc-agent-1",
            capability="read_orders",
            scope=("orders:read", "orders:list"),
            ttl_seconds=300,
        )
        self.grant = self.authority.issue(self.request, now_epoch=1_000)

    def test_in_scope_valid_grant_accepted(self) -> None:
        self.assertTrue(
            self.authority.check(
                self.grant, "read_orders", ("orders:read",), when_epoch=1_100
            )
        )

    def test_exact_scope_match_accepted(self) -> None:
        self.assertTrue(
            self.authority.check(
                self.grant,
                "read_orders",
                ("orders:read", "orders:list"),
                when_epoch=1_100,
            )
        )

    def test_empty_scope_needed_accepted(self) -> None:
        self.assertTrue(
            self.authority.check(self.grant, "read_orders", (), when_epoch=1_100)
        )

    def test_expired_grant_rejected(self) -> None:
        self.assertFalse(
            self.authority.check(
                self.grant, "read_orders", ("orders:read",), when_epoch=1_300
            )
        )

    def test_grant_valid_one_second_before_expiry(self) -> None:
        self.assertTrue(
            self.authority.check(
                self.grant, "read_orders", ("orders:read",), when_epoch=1_299
            )
        )

    def test_over_scoped_request_rejected(self) -> None:
        self.assertFalse(
            self.authority.check(
                self.grant,
                "read_orders",
                ("orders:read", "orders:delete"),
                when_epoch=1_100,
            )
        )

    def test_wrong_capability_rejected(self) -> None:
        self.assertFalse(
            self.authority.check(
                self.grant, "delete_orders", ("orders:read",), when_epoch=1_100
            )
        )

    def test_revoked_grant_rejected(self) -> None:
        revoked = self.authority.revoke(self.grant)
        self.assertTrue(revoked.revoked)
        self.assertFalse(
            self.authority.check(
                revoked, "read_orders", ("orders:read",), when_epoch=1_100
            )
        )

    def test_revoke_returns_new_object_original_unchanged(self) -> None:
        revoked = self.authority.revoke(self.grant)
        self.assertFalse(self.grant.revoked)
        self.assertIsNot(revoked, self.grant)

    def test_revoked_grant_rejected_even_when_still_within_ttl(self) -> None:
        revoked = self.authority.revoke(self.grant)
        self.assertFalse(
            self.authority.check(
                revoked, "read_orders", ("orders:read",), when_epoch=1_001
            )
        )


if __name__ == "__main__":
    unittest.main()
