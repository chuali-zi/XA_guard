from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.p2.base import CapabilityStatus
from enterprise_agent_range.p2.remediation import (
    SPEC,
    CompensatingAction,
    RemediationPlanner,
    UndoLog,
)


class RemediationSpecTest(unittest.TestCase):
    def test_spec_is_implemented(self) -> None:
        self.assertEqual(SPEC.key, "remediation")
        self.assertEqual(SPEC.module, "enterprise_agent_range.p2.remediation")
        self.assertEqual(SPEC.status, CapabilityStatus.IMPLEMENTED)


class EmptyInputTest(unittest.TestCase):
    def test_empty_side_effects_returns_empty_undo_log(self) -> None:
        log = RemediationPlanner().plan([], trace_id="trace-empty")
        self.assertEqual(log, UndoLog(trace_id="trace-empty", actions=()))
        self.assertEqual(log.actions, ())


class OneActionPerCommittedEffectTest(unittest.TestCase):
    def test_one_action_per_committed_row(self) -> None:
        side_effects = [
            {"sink_type": "payment", "operation": "submit_payment_request", "payload_hash": "h1", "committed": True},
            {"sink_type": "mail", "operation": "send_email", "payload_hash": "h2", "committed": True},
            {"sink_type": "plugin", "operation": "install_plugin", "payload_hash": "h3", "committed": True},
        ]
        log = RemediationPlanner().plan(side_effects, trace_id="trace-1")
        self.assertEqual(len(log.actions), 3)
        self.assertEqual(log.trace_id, "trace-1")

    def test_uncommitted_effects_are_ignored(self) -> None:
        side_effects = [
            {"sink_type": "payment", "operation": "submit_payment_request", "payload_hash": "h1", "committed": True},
            {"sink_type": "mail", "operation": "send_email", "payload_hash": "h2", "committed": False},
        ]
        log = RemediationPlanner().plan(side_effects)
        self.assertEqual(len(log.actions), 1)
        self.assertEqual(log.actions[0].target_side_effect_hash, "h1")

    def test_all_uncommitted_yields_empty_log(self) -> None:
        side_effects = [
            {"sink_type": "payment", "payload_hash": "h1", "committed": False},
            {"sink_type": "mail", "payload_hash": "h2", "committed": False},
        ]
        log = RemediationPlanner().plan(side_effects)
        self.assertEqual(log.actions, ())

    def test_missing_committed_key_treated_as_uncommitted(self) -> None:
        side_effects = [{"sink_type": "payment", "payload_hash": "h1"}]
        log = RemediationPlanner().plan(side_effects)
        self.assertEqual(log.actions, ())


class ReversibilityTest(unittest.TestCase):
    def test_email_sink_flagged_irreversible(self) -> None:
        side_effects = [{"sink_type": "email", "payload_hash": "h1", "committed": True}]
        action = RemediationPlanner().plan(side_effects).actions[0]
        self.assertFalse(action.reversible)
        self.assertEqual(action.description, "send retraction notice")

    def test_mail_alias_flagged_irreversible(self) -> None:
        side_effects = [{"sink_type": "mail", "payload_hash": "h1", "committed": True}]
        action = RemediationPlanner().plan(side_effects).actions[0]
        self.assertFalse(action.reversible)

    def test_http_sink_flagged_irreversible(self) -> None:
        side_effects = [{"sink_type": "http", "payload_hash": "h1", "committed": True}]
        action = RemediationPlanner().plan(side_effects).actions[0]
        self.assertFalse(action.reversible)
        self.assertEqual(action.description, "revoke/rotate exposed token")

    def test_payment_sink_flagged_reversible(self) -> None:
        side_effects = [{"sink_type": "payment", "payload_hash": "h1", "committed": True}]
        action = RemediationPlanner().plan(side_effects).actions[0]
        self.assertTrue(action.reversible)
        self.assertEqual(action.description, "submit reversal/hold request")

    def test_plugin_sink_flagged_reversible(self) -> None:
        side_effects = [{"sink_type": "plugin", "payload_hash": "h1", "committed": True}]
        action = RemediationPlanner().plan(side_effects).actions[0]
        self.assertTrue(action.reversible)
        self.assertEqual(action.description, "quarantine and uninstall")

    def test_service_sink_flagged_reversible(self) -> None:
        side_effects = [{"sink_type": "service", "payload_hash": "h1", "committed": True}]
        action = RemediationPlanner().plan(side_effects).actions[0]
        self.assertTrue(action.reversible)
        self.assertEqual(action.description, "restore previous service state")

    def test_notification_sink_flagged_reversible(self) -> None:
        side_effects = [{"sink_type": "notification", "payload_hash": "h1", "committed": True}]
        action = RemediationPlanner().plan(side_effects).actions[0]
        self.assertTrue(action.reversible)
        self.assertEqual(action.description, "post correction notice")

    def test_unknown_sink_defaults_to_manual_review_and_irreversible(self) -> None:
        side_effects = [{"sink_type": "command", "payload_hash": "h1", "committed": True}]
        action = RemediationPlanner().plan(side_effects).actions[0]
        self.assertEqual(action.description, "manual review")
        self.assertFalse(action.reversible)


class ActionIdTest(unittest.TestCase):
    def test_action_id_deterministic_for_same_input(self) -> None:
        row = {"sink_type": "payment", "payload_hash": "h1", "committed": True}
        first = RemediationPlanner().plan([row]).actions[0]
        second = RemediationPlanner().plan([row]).actions[0]
        self.assertEqual(first.action_id, second.action_id)
        self.assertTrue(first.action_id.startswith("undo-"))

    def test_action_id_differs_for_different_payload_hash(self) -> None:
        row_a = {"sink_type": "payment", "payload_hash": "h1", "committed": True}
        row_b = {"sink_type": "payment", "payload_hash": "h2", "committed": True}
        action_a = RemediationPlanner().plan([row_a]).actions[0]
        action_b = RemediationPlanner().plan([row_b]).actions[0]
        self.assertNotEqual(action_a.action_id, action_b.action_id)

    def test_action_id_differs_for_different_sink_type(self) -> None:
        row_a = {"sink_type": "payment", "payload_hash": "h1", "committed": True}
        row_b = {"sink_type": "mail", "payload_hash": "h1", "committed": True}
        action_a = RemediationPlanner().plan([row_a]).actions[0]
        action_b = RemediationPlanner().plan([row_b]).actions[0]
        self.assertNotEqual(action_a.action_id, action_b.action_id)

    def test_action_id_differs_for_same_payload_in_different_traces(self) -> None:
        side_effects = [
            {
                "sink_type": "ticket",
                "operation": "submit_approval",
                "payload_hash": "sha256:same-payload",
                "trace_id": "trace-1",
                "committed": True,
            },
            {
                "sink_type": "ticket",
                "operation": "submit_approval",
                "payload_hash": "sha256:same-payload",
                "trace_id": "trace-2",
                "committed": True,
            },
        ]
        actions = RemediationPlanner().plan(side_effects).actions
        self.assertEqual(len(actions), 2)
        self.assertEqual(len({action.action_id for action in actions}), 2)
        self.assertEqual(
            {action.metadata["trace_id"] for action in actions},
            {"trace-1", "trace-2"},
        )

    def test_target_side_effect_hash_references_payload_hash(self) -> None:
        row = {"sink_type": "payment", "payload_hash": "sha256:abc", "committed": True}
        action = RemediationPlanner().plan([row]).actions[0]
        self.assertEqual(action.target_side_effect_hash, "sha256:abc")


class OrderingTest(unittest.TestCase):
    def test_actions_sorted_by_action_id(self) -> None:
        side_effects = [
            {"sink_type": "plugin", "payload_hash": "h3", "committed": True},
            {"sink_type": "payment", "payload_hash": "h1", "committed": True},
            {"sink_type": "mail", "payload_hash": "h2", "committed": True},
        ]
        log = RemediationPlanner().plan(side_effects)
        ids = [action.action_id for action in log.actions]
        self.assertEqual(ids, sorted(ids))

    def test_ordering_independent_of_input_order(self) -> None:
        side_effects = [
            {"sink_type": "plugin", "payload_hash": "h3", "committed": True},
            {"sink_type": "payment", "payload_hash": "h1", "committed": True},
            {"sink_type": "mail", "payload_hash": "h2", "committed": True},
        ]
        log_forward = RemediationPlanner().plan(side_effects)
        log_reversed = RemediationPlanner().plan(list(reversed(side_effects)))
        forward_hashes = [a.target_side_effect_hash for a in log_forward.actions]
        reversed_hashes = [a.target_side_effect_hash for a in log_reversed.actions]
        self.assertEqual(forward_hashes, reversed_hashes)

    def test_duplicate_payload_ordering_independent_of_input_order(self) -> None:
        side_effects = [
            {"sink_type": "ticket", "payload_hash": "same", "trace_id": "trace-1", "committed": True},
            {"sink_type": "ticket", "payload_hash": "same", "trace_id": "trace-2", "committed": True},
        ]
        log_forward = RemediationPlanner().plan(side_effects)
        log_reversed = RemediationPlanner().plan(list(reversed(side_effects)))
        self.assertEqual(
            [action.action_id for action in log_forward.actions],
            [action.action_id for action in log_reversed.actions],
        )


class DeterminismTest(unittest.TestCase):
    def test_same_input_yields_identical_undo_log(self) -> None:
        side_effects = [
            {"sink_type": "payment", "operation": "submit_payment_request", "payload_hash": "h1", "committed": True},
            {"sink_type": "mail", "operation": "send_email", "payload_hash": "h2", "committed": True},
        ]
        planner = RemediationPlanner()
        first = planner.plan(side_effects, trace_id="trace-det")
        second = planner.plan(side_effects, trace_id="trace-det")
        self.assertEqual(first, second)


class RealisticSideEffectsTest(unittest.TestCase):
    def test_p1_style_rows_produce_expected_plan(self) -> None:
        # Shaped like reports/run-p1-null-verify/side-effects.jsonl rows for
        # trace-P1-A-002 (mail) and trace-P1-A-004 (command).
        side_effects = [
            {
                "committed": True,
                "operation": "send_email",
                "payload_hash": "sha256:6e873a03f9b1c4c2ab8600d2d13a9b880f8e92649140f5601987f8294b025b80",
                "sink_type": "mail",
                "trace_id": "trace-P1-A-002-bc890df9db",
            },
            {
                "committed": True,
                "operation": "restart_service",
                "payload_hash": "sha256:9b15f49b724365c3621e7c649d200ffd3a35be07b0335128eed2a43a42931c25",
                "sink_type": "command",
                "trace_id": "trace-P1-A-004-241b15aea9",
            },
        ]
        log = RemediationPlanner().plan(side_effects, trace_id="trace-P1-A-002-bc890df9db")
        self.assertEqual(len(log.actions), 2)
        mail_action = next(a for a in log.actions if a.metadata["sink_type"] == "mail")
        self.assertFalse(mail_action.reversible)
        self.assertEqual(mail_action.description, "send retraction notice")
        self.assertIsInstance(mail_action, CompensatingAction)


if __name__ == "__main__":
    unittest.main()
