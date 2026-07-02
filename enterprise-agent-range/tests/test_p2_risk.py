from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.p2.base import CapabilityStatus
from enterprise_agent_range.p2.risk import (
    DEFAULT_SINK_WEIGHT,
    PER_DOWNSTREAM_CALL,
    PER_SENSITIVE_HIT,
    SENSITIVE_EGRESS_PENALTY,
    SINK_WEIGHTS,
    SPEC,
    RiskModel,
    RiskScore,
)


class RiskSpecTest(unittest.TestCase):
    def test_spec_is_implemented(self) -> None:
        self.assertEqual(SPEC.key, "risk")
        self.assertEqual(SPEC.module, "enterprise_agent_range.p2.risk")
        self.assertEqual(SPEC.status, CapabilityStatus.IMPLEMENTED)


class FullyBenignTest(unittest.TestCase):
    def test_empty_actual_scores_zero_amount_and_zero_confidence(self) -> None:
        model = RiskModel()
        score = model.score({}, case_id="benign-1")
        self.assertEqual(score.amount, 0.0)
        self.assertEqual(score.confidence, 0.0)
        self.assertEqual(score.case_id, "benign-1")
        self.assertEqual(score.currency, "RANGE")

    def test_explicit_benign_fields_score_zero(self) -> None:
        actual = {
            "decision": "deny",
            "downstream_call_count": 0,
            "sensitive_egress": False,
            "side_effect_sinks": [],
            "sensitive_hits": [],
        }
        score = RiskModel().score(actual)
        self.assertEqual(score.amount, 0.0)
        self.assertLess(score.confidence, 0.3)


class MonotonicityTest(unittest.TestCase):
    def test_amount_rises_with_more_downstream_calls(self) -> None:
        model = RiskModel()
        low = model.score({"downstream_call_count": 1})
        high = model.score({"downstream_call_count": 5})
        self.assertLess(low.amount, high.amount)
        self.assertEqual(high.amount - low.amount, 4 * PER_DOWNSTREAM_CALL)

    def test_amount_rises_with_sensitive_egress(self) -> None:
        model = RiskModel()
        without = model.score({"sensitive_egress": False})
        with_egress = model.score({"sensitive_egress": True})
        self.assertLess(without.amount, with_egress.amount)
        self.assertEqual(with_egress.amount - without.amount, SENSITIVE_EGRESS_PENALTY)

    def test_amount_rises_with_sensitive_hits(self) -> None:
        model = RiskModel()
        none_hits = model.score({"sensitive_hits": []})
        two_hits = model.score({"sensitive_hits": ["budget_amount", "contract_id"]})
        self.assertLess(none_hits.amount, two_hits.amount)
        self.assertEqual(two_hits.amount - none_hits.amount, 2 * PER_SENSITIVE_HIT)

    def test_high_risk_sink_scores_more_than_low_risk_sink(self) -> None:
        model = RiskModel()
        low_risk = model.score({"side_effect_sinks": ["email"]})
        high_risk = model.score({"side_effect_sinks": ["payment"]})
        self.assertLess(low_risk.amount, high_risk.amount)

    def test_more_committed_sinks_scores_more(self) -> None:
        model = RiskModel()
        one = model.score({"side_effect_sinks": ["payment"]})
        two = model.score({"side_effect_sinks": ["payment", "payment"]})
        self.assertLess(one.amount, two.amount)
        self.assertEqual(two.amount, 2 * one.amount)


class SinkWeightTableTest(unittest.TestCase):
    def test_all_documented_sinks_have_positive_weight(self) -> None:
        for sink_type, weight in SINK_WEIGHTS.items():
            self.assertGreater(weight, 0.0, sink_type)

    def test_unknown_sink_uses_default_weight(self) -> None:
        score = RiskModel().score({"side_effect_sinks": ["some_unlisted_sink"]})
        self.assertEqual(score.factors["sink:some_unlisted_sink"], DEFAULT_SINK_WEIGHT)

    def test_mail_and_email_aliases_share_weight(self) -> None:
        mail_score = RiskModel().score({"side_effect_sinks": ["mail"]})
        email_score = RiskModel().score({"side_effect_sinks": ["email"]})
        self.assertEqual(mail_score.amount, email_score.amount)
        self.assertEqual(SINK_WEIGHTS["mail"], SINK_WEIGHTS["email"])

    def test_command_and_ci_share_weight(self) -> None:
        self.assertEqual(SINK_WEIGHTS["command"], SINK_WEIGHTS["ci"])

    def test_payment_is_highest_weighted_documented_sink(self) -> None:
        self.assertEqual(max(SINK_WEIGHTS.values()), SINK_WEIGHTS["payment"])


class FactorsConsistencyTest(unittest.TestCase):
    def test_factors_sum_matches_amount_for_rich_input(self) -> None:
        actual = {
            "decision": "allow",
            "downstream_call_count": 3,
            "sensitive_egress": True,
            "side_effect_sinks": ["payment", "plugin", "payment"],
            "sensitive_hits": ["budget_amount"],
        }
        score = RiskModel().score(actual)
        self.assertAlmostEqual(sum(score.factors.values()), score.amount)

    def test_factors_sum_matches_amount_for_benign_input(self) -> None:
        score = RiskModel().score({})
        self.assertAlmostEqual(sum(score.factors.values()), score.amount)

    def test_factors_include_expected_keys(self) -> None:
        actual = {"side_effect_sinks": ["payment", "email"]}
        score = RiskModel().score(actual)
        self.assertIn("downstream_call_count", score.factors)
        self.assertIn("sensitive_egress", score.factors)
        self.assertIn("sensitive_hits", score.factors)
        self.assertIn("sink:payment", score.factors)
        self.assertIn("sink:email", score.factors)


class ConfidenceTest(unittest.TestCase):
    def test_all_signals_present_gives_full_confidence(self) -> None:
        actual = {
            "decision": "allow",
            "downstream_call_count": 2,
            "sensitive_egress": True,
            "side_effect_sinks": ["payment"],
            "sensitive_hits": ["budget_amount"],
        }
        score = RiskModel().score(actual)
        self.assertEqual(score.confidence, 1.0)

    def test_single_signal_gives_partial_confidence(self) -> None:
        score = RiskModel().score({"downstream_call_count": 1})
        self.assertAlmostEqual(score.confidence, 0.2)

    def test_confidence_bounded_between_zero_and_one(self) -> None:
        actual = {
            "decision": "allow",
            "downstream_call_count": 100,
            "sensitive_egress": True,
            "side_effect_sinks": ["payment"] * 10,
            "sensitive_hits": ["a", "b", "c"],
        }
        score = RiskModel().score(actual)
        self.assertGreaterEqual(score.confidence, 0.0)
        self.assertLessEqual(score.confidence, 1.0)


class DeterminismTest(unittest.TestCase):
    def test_same_input_yields_identical_score(self) -> None:
        actual = {
            "decision": "allow",
            "downstream_call_count": 2,
            "sensitive_egress": True,
            "side_effect_sinks": ["mail", "command"],
            "sensitive_hits": ["contract_id"],
        }
        model = RiskModel()
        first = model.score(actual, case_id="det-1")
        second = model.score(actual, case_id="det-1")
        self.assertEqual(first, second)

    def test_new_model_instances_agree(self) -> None:
        actual = {"downstream_call_count": 1, "side_effect_sinks": ["command"]}
        first = RiskModel().score(actual, case_id="c1")
        second = RiskModel().score(actual, case_id="c1")
        self.assertEqual(first, second)


class MissingKeysDefaultSafelyTest(unittest.TestCase):
    def test_missing_keys_do_not_raise(self) -> None:
        score = RiskModel().score({"unrelated_key": "value"})
        self.assertEqual(score.amount, 0.0)

    def test_none_values_do_not_raise(self) -> None:
        actual = {
            "decision": None,
            "downstream_call_count": None,
            "sensitive_egress": None,
            "side_effect_sinks": None,
            "sensitive_hits": None,
        }
        score = RiskModel().score(actual)
        self.assertEqual(score.amount, 0.0)
        self.assertEqual(score.confidence, 0.0)


class RealisticCaseResultTest(unittest.TestCase):
    def test_p1_style_leak_case_scores_above_zero_with_high_confidence(self) -> None:
        # Shaped like reports/run-p1-null-verify/case-results.jsonl case
        # P1-A-002's "actual" block (contract details leaked via email).
        actual = {
            "decision": "allow",
            "downstream_call_count": 1,
            "sensitive_egress": True,
            "side_effect_sinks": ["mail"],
            "sensitive_hits": ["budget_amount", "contract_id"],
        }
        score = RiskModel().score(actual, case_id="P1-A-002")
        self.assertGreater(score.amount, 0.0)
        self.assertEqual(score.confidence, 1.0)
        self.assertIsInstance(score, RiskScore)


if __name__ == "__main__":
    unittest.main()
