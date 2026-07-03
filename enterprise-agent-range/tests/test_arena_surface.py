import tempfile
import unittest
from pathlib import Path

from enterprise_agent_range.arena.surface import office_tool_surface, write_gate4_capabilities


class TestArenaSurface(unittest.TestCase):
    def test_office_surface_exposes_three_mcp_tools(self):
        surface = office_tool_surface()

        self.assertEqual(surface.name, "office-baseline")
        self.assertEqual(set(surface.tool_names()), {"read_mail", "query_project", "send_email"})

        schemas = {item["name"]: item for item in surface.mcp_tool_schemas()}
        self.assertEqual(schemas["read_mail"]["inputSchema"]["properties"], {})
        self.assertEqual(schemas["query_project"]["inputSchema"]["required"], ["project_id"])
        self.assertEqual(schemas["send_email"]["inputSchema"]["required"], ["to", "body"])

    def test_gate4_capability_yaml_includes_risk_capability_and_taint_metadata(self):
        text = office_tool_surface().gate4_capability_document()

        self.assertIn("tool_name: read_mail", text)
        self.assertIn("capabilities: [\"NETWORK_INTERNAL\", \"FS_READ\"]", text)
        self.assertIn("tool_name: query_project", text)
        self.assertIn("output_taint: CONFIDENTIAL", text)
        self.assertIn("tool_name: send_email", text)
        self.assertIn("capabilities: [\"NETWORK_EXTERNAL\", \"NOTIFY\"]", text)
        self.assertIn("input_max_taint: INTERNAL", text)
        self.assertIn("risk_level: yellow", text)

    def test_write_gate4_capabilities_appends_to_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            baseline = root / "baseline.yaml"
            baseline.write_text("tools:\n  - tool_name: existing\n", encoding="utf-8")
            generated = root / "generated.yaml"

            write_gate4_capabilities(generated, baseline)

            text = generated.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("tools:\n  - tool_name: existing"))
            self.assertIn("Enterprise Agent Range office-baseline tools", text)
            self.assertIn("tool_name: read_mail", text)
            self.assertIn("tool_name: query_project", text)
            self.assertIn("tool_name: send_email", text)


if __name__ == "__main__":
    unittest.main()
