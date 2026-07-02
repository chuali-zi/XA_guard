import unittest
from pathlib import Path

from enterprise_agent_range.arena.agent_seat import GullibleAgent
from enterprise_agent_range.arena.challenge import load_challenge
from enterprise_agent_range.arena.run import run_challenge
from enterprise_agent_range.arena.sut import GuardStubSUT, NullSUT

ROOT = Path(__file__).resolve().parents[1]
ATTACK = ROOT / "cases/arena/OFFICE-INJ-001.attack.json"
CONTROL = ROOT / "cases/arena/OFFICE-INJ-001.control.json"


class TestEndToEnd(unittest.TestCase):
    def test_attack_and_control_share_task_and_world(self):
        attack = load_challenge(ATTACK)
        control = load_challenge(CONTROL)
        # DoD: 环境与题库解耦——同 world、同中性任务，仅 inject 不同。
        self.assertEqual(attack.world, control.world)
        self.assertEqual(attack.task.prompt, control.task.prompt)
        self.assertTrue(attack.inject)
        self.assertEqual(control.inject, [])

    def test_2x2_matrix(self):
        attack = load_challenge(ATTACK)
        control = load_challenge(CONTROL)

        attack_guard = run_challenge(attack, GullibleAgent(), GuardStubSUT(), ROOT)
        attack_null = run_challenge(attack, GullibleAgent(), NullSUT(), ROOT)
        control_guard = run_challenge(control, GullibleAgent(), GuardStubSUT(), ROOT)
        control_null = run_challenge(control, GullibleAgent(), NullSUT(), ROOT)

        # GuardStub 拦住攻击；Null 放行导致外泄 -> A/B 防护差值可见
        self.assertTrue(attack_guard.verdict.passed)
        self.assertFalse(attack_null.verdict.passed)
        self.assertTrue(attack_null.verdict.data_exposure)
        # 良性对照在两种 SUT 下都放行（无误报）
        self.assertTrue(control_guard.verdict.passed)
        self.assertTrue(control_null.verdict.passed)

    def test_evidence_contains_audit_and_hash(self):
        attack = load_challenge(ATTACK)
        result = run_challenge(attack, GullibleAgent(), GuardStubSUT(), ROOT)
        self.assertEqual(result.evidence["sut_id"], "guard-stub")
        self.assertIn("audit", result.evidence)
        self.assertTrue(result.evidence["trace_hash"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
