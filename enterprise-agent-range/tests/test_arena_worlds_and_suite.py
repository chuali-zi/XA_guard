import tempfile
import unittest
from pathlib import Path

from enterprise_agent_range.arena.suite import default_suite, load_suite, suite_to_json
from enterprise_agent_range.arena.worlds import get_world_spec, list_worlds


class TestArenaWorldsAndSuite(unittest.TestCase):
    def test_office_world_spec_builds_world(self):
        spec = get_world_spec("office-baseline")
        world = spec.build()
        self.assertEqual(spec.default_principal, "bob.employee@range.local")
        self.assertIn("mailbox:bob.employee@range.local", spec.injection_targets)
        self.assertIn("PRJ-ATLAS", world.projects)
        self.assertEqual([item.world_id for item in list_worlds()], ["office-baseline"])

    def test_default_suite_points_to_attack_and_control(self):
        suite = default_suite()
        self.assertEqual(suite.suite_id, "office-mail-smoke")
        self.assertEqual(len(suite.challenge_paths), 2)
        self.assertIn("OFFICE-INJ-001.attack.json", suite.challenge_paths[0].as_posix())
        self.assertEqual(suite_to_json(suite)["suite_id"], "office-mail-smoke")

    def test_load_suite_resolves_relative_paths(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "suite.json"
            path.write_text('{"suite_id":"s","challenge_paths":["cases/a.json"]}', encoding="utf-8")
            suite = load_suite(path)
            self.assertEqual(suite.resolved_paths(root), [root / "cases/a.json"])


if __name__ == "__main__":
    unittest.main()