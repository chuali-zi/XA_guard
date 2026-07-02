from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.p2 import evidence
from enterprise_agent_range.p2.base import CapabilityStatus


class TimestampAuthorityTest(unittest.TestCase):
    def test_stamp_then_verify_round_trips_true(self) -> None:
        tsa = evidence.TimestampAuthority()
        token = tsa.stamp("sha256:deadbeef", at="2026-07-02T00:00:00Z")
        self.assertEqual(token.evidence_hash, "sha256:deadbeef")
        self.assertEqual(token.timestamp, "2026-07-02T00:00:00Z")
        self.assertEqual(token.authority, "mock-tsa")
        self.assertTrue(token.token_ref)
        self.assertTrue(tsa.verify(token))

    def test_stamp_is_deterministic(self) -> None:
        tsa = evidence.TimestampAuthority()
        token_a = tsa.stamp("sha256:same", at="2026-07-02T00:00:00Z")
        token_b = tsa.stamp("sha256:same", at="2026-07-02T00:00:00Z")
        self.assertEqual(token_a.token_ref, token_b.token_ref)

    def test_tampered_evidence_hash_fails_verify(self) -> None:
        tsa = evidence.TimestampAuthority()
        token = tsa.stamp("sha256:original", at="2026-07-02T00:00:00Z")
        tampered = replace(token, evidence_hash="sha256:tampered")
        self.assertFalse(tsa.verify(tampered))

    def test_tampered_timestamp_fails_verify(self) -> None:
        tsa = evidence.TimestampAuthority()
        token = tsa.stamp("sha256:original", at="2026-07-02T00:00:00Z")
        tampered = replace(token, timestamp="2099-01-01T00:00:00Z")
        self.assertFalse(tsa.verify(tampered))

    def test_tampered_token_ref_fails_verify(self) -> None:
        tsa = evidence.TimestampAuthority()
        token = tsa.stamp("sha256:original", at="2026-07-02T00:00:00Z")
        tampered = replace(token, token_ref="0" * 64)
        self.assertFalse(tsa.verify(tampered))


class HsmSignerTest(unittest.TestCase):
    def test_sign_is_deterministic(self) -> None:
        signer = evidence.HsmSigner()
        payload = b"evidence-bundle-bytes"
        result_a = signer.sign(payload)
        result_b = signer.sign(payload)
        self.assertEqual(result_a, result_b)
        self.assertEqual(result_a["algo"], "HMAC-SHA256(mock-hsm)")
        self.assertEqual(result_a["key_id"], "mock-hsm-key")
        self.assertTrue(result_a["signature"])

    def test_verify_true_for_matching_signature(self) -> None:
        signer = evidence.HsmSigner()
        payload = b"evidence-bundle-bytes"
        signed = signer.sign(payload)
        self.assertTrue(signer.verify(payload, signed["signature"]))

    def test_verify_false_for_wrong_signature(self) -> None:
        signer = evidence.HsmSigner()
        payload = b"evidence-bundle-bytes"
        self.assertFalse(signer.verify(payload, "0" * 64))

    def test_verify_false_for_tampered_payload(self) -> None:
        signer = evidence.HsmSigner()
        signed = signer.sign(b"original-payload")
        self.assertFalse(signer.verify(b"tampered-payload", signed["signature"]))


class MockKeyConstantsTest(unittest.TestCase):
    def test_keys_are_obviously_fake_mock_constants(self) -> None:
        self.assertEqual(evidence._MOCK_TSA_KEY, b"range-mock-tsa-key")
        self.assertEqual(evidence._MOCK_HSM_KEY, b"range-mock-hsm-key")


class EvidenceSpecTest(unittest.TestCase):
    def test_spec_reports_implemented(self) -> None:
        self.assertEqual(evidence.SPEC.key, "evidence")
        self.assertEqual(evidence.SPEC.module, evidence.__name__)
        self.assertEqual(evidence.SPEC.status, CapabilityStatus.IMPLEMENTED)


if __name__ == "__main__":
    unittest.main()
