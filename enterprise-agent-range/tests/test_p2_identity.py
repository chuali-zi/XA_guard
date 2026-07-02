from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.p2.base import CapabilityStatus
from enterprise_agent_range.p2.identity import (
    ACTIONABLE_STATES,
    ALLOWED_TRANSITIONS,
    SPEC,
    AgentIdentity,
    IdentityLifecycle,
    IdentityRegistry,
    IdentityState,
)


class IdentitySpecTest(unittest.TestCase):
    def test_spec_is_implemented(self) -> None:
        self.assertEqual(SPEC.key, "identity")
        self.assertEqual(SPEC.status, CapabilityStatus.IMPLEMENTED)


class TransitionTableTest(unittest.TestCase):
    def test_all_states_have_a_transition_entry(self) -> None:
        self.assertEqual(set(ALLOWED_TRANSITIONS.keys()), set(IdentityState.ALL))

    def test_retired_is_terminal(self) -> None:
        self.assertEqual(ALLOWED_TRANSITIONS[IdentityState.RETIRED], frozenset())


class IdentityLifecycleTransitionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lifecycle = IdentityLifecycle()

    def test_provisioned_to_active_allowed(self) -> None:
        identity = AgentIdentity(agent_id="agent-1")
        new_identity = self.lifecycle.transition(identity, IdentityState.ACTIVE)
        self.assertEqual(new_identity.state, IdentityState.ACTIVE)
        self.assertEqual(new_identity.agent_id, "agent-1")
        # original is untouched (frozen dataclass, new instance returned)
        self.assertEqual(identity.state, IdentityState.PROVISIONED)

    def test_provisioned_to_suspended_illegal(self) -> None:
        identity = AgentIdentity(agent_id="agent-1")
        with self.assertRaises(ValueError):
            self.lifecycle.transition(identity, IdentityState.SUSPENDED)

    def test_active_to_rotated_allowed_and_changes_credential(self) -> None:
        identity = AgentIdentity(
            agent_id="agent-1", state=IdentityState.ACTIVE, credential_ref="cred-abc"
        )
        rotated = self.lifecycle.transition(identity, IdentityState.ROTATED)
        self.assertEqual(rotated.state, IdentityState.ROTATED)
        self.assertEqual(rotated.credential_ref, "cred-abc-r1")

    def test_rotate_twice_increments_deterministic_counter(self) -> None:
        identity = AgentIdentity(
            agent_id="agent-1", state=IdentityState.ACTIVE, credential_ref="cred-abc"
        )
        once = self.lifecycle.transition(identity, IdentityState.ROTATED)
        # rotated -> active -> rotated again
        back_active = self.lifecycle.transition(once, IdentityState.ACTIVE)
        twice = self.lifecycle.transition(back_active, IdentityState.ROTATED)
        self.assertEqual(once.credential_ref, "cred-abc-r1")
        self.assertEqual(twice.credential_ref, "cred-abc-r2")

    def test_rotation_is_deterministic_for_same_input(self) -> None:
        identity = AgentIdentity(
            agent_id="agent-1", state=IdentityState.ACTIVE, credential_ref="cred-xyz"
        )
        first = self.lifecycle.transition(identity, IdentityState.ROTATED)
        second = self.lifecycle.transition(identity, IdentityState.ROTATED)
        self.assertEqual(first, second)

    def test_active_to_suspended_and_back_to_active(self) -> None:
        identity = AgentIdentity(agent_id="agent-1", state=IdentityState.ACTIVE)
        suspended = self.lifecycle.transition(identity, IdentityState.SUSPENDED)
        self.assertEqual(suspended.state, IdentityState.SUSPENDED)
        reactivated = self.lifecycle.transition(suspended, IdentityState.ACTIVE)
        self.assertEqual(reactivated.state, IdentityState.ACTIVE)

    def test_revoked_to_retired_allowed(self) -> None:
        identity = AgentIdentity(agent_id="agent-1", state=IdentityState.REVOKED)
        retired = self.lifecycle.transition(identity, IdentityState.RETIRED)
        self.assertEqual(retired.state, IdentityState.RETIRED)

    def test_revoked_to_active_illegal(self) -> None:
        identity = AgentIdentity(agent_id="agent-1", state=IdentityState.REVOKED)
        with self.assertRaises(ValueError):
            self.lifecycle.transition(identity, IdentityState.ACTIVE)

    def test_retired_is_terminal_for_all_targets(self) -> None:
        identity = AgentIdentity(agent_id="agent-1", state=IdentityState.RETIRED)
        for target in IdentityState.ALL:
            with self.assertRaises(ValueError):
                self.lifecycle.transition(identity, target)

    def test_unknown_target_state_raises_value_error(self) -> None:
        identity = AgentIdentity(agent_id="agent-1", state=IdentityState.ACTIVE)
        with self.assertRaises(ValueError):
            self.lifecycle.transition(identity, "not-a-real-state")

    def test_suspended_to_revoked_allowed(self) -> None:
        identity = AgentIdentity(agent_id="agent-1", state=IdentityState.SUSPENDED)
        revoked = self.lifecycle.transition(identity, IdentityState.REVOKED)
        self.assertEqual(revoked.state, IdentityState.REVOKED)

    def test_rotated_to_suspended_allowed(self) -> None:
        identity = AgentIdentity(
            agent_id="agent-1", state=IdentityState.ROTATED, credential_ref="cred-r1"
        )
        suspended = self.lifecycle.transition(identity, IdentityState.SUSPENDED)
        self.assertEqual(suspended.state, IdentityState.SUSPENDED)
        # credential unaffected by non-rotation transitions
        self.assertEqual(suspended.credential_ref, "cred-r1")


class CanActTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lifecycle = IdentityLifecycle()

    def test_can_act_true_for_active_and_rotated(self) -> None:
        for state in (IdentityState.ACTIVE, IdentityState.ROTATED):
            identity = AgentIdentity(agent_id="agent-1", state=state)
            self.assertTrue(self.lifecycle.can_act(identity), state)

    def test_can_act_false_for_all_other_states(self) -> None:
        for state in IdentityState.ALL:
            if state in ACTIONABLE_STATES:
                continue
            identity = AgentIdentity(agent_id="agent-1", state=state)
            self.assertFalse(self.lifecycle.can_act(identity), state)

    def test_can_act_false_for_revoked_after_transition(self) -> None:
        identity = AgentIdentity(agent_id="agent-1", state=IdentityState.ACTIVE)
        revoked = self.lifecycle.transition(identity, IdentityState.REVOKED)
        self.assertFalse(self.lifecycle.can_act(revoked))


class IdentityRegistryTest(unittest.TestCase):
    def test_register_and_get(self) -> None:
        registry = IdentityRegistry()
        identity = AgentIdentity(agent_id="agent-42")
        registry.register(identity)
        self.assertEqual(registry.get("agent-42"), identity)

    def test_get_unknown_raises_key_error(self) -> None:
        registry = IdentityRegistry()
        with self.assertRaises(KeyError):
            registry.get("does-not-exist")

    def test_list_returns_all_registered(self) -> None:
        registry = IdentityRegistry()
        a = AgentIdentity(agent_id="agent-a")
        b = AgentIdentity(agent_id="agent-b")
        registry.register(a)
        registry.register(b)
        listed = registry.list()
        self.assertEqual(len(listed), 2)
        self.assertIn(a, listed)
        self.assertIn(b, listed)

    def test_register_overwrites_existing(self) -> None:
        registry = IdentityRegistry()
        registry.register(AgentIdentity(agent_id="agent-1", state=IdentityState.PROVISIONED))
        registry.register(AgentIdentity(agent_id="agent-1", state=IdentityState.ACTIVE))
        self.assertEqual(registry.get("agent-1").state, IdentityState.ACTIVE)


if __name__ == "__main__":
    unittest.main()
