from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.systems import RangeState, ToolContext
from enterprise_agent_range.tools import TOOL_DEFINITIONS, TOOL_HANDLERS, execute_tool


class ToolSurfaceTest(unittest.TestCase):
    def test_p0_tool_surface_has_required_weight(self) -> None:
        self.assertGreaterEqual(len(TOOL_DEFINITIONS), 20)
        for name in [
            "read_mail",
            "send_email",
            "restart_service",
            "exec_command",
            "query_contract",
            "install_plugin",
            "verify_audit",
            "submit_payment_request",
        ]:
            self.assertIn(name, TOOL_DEFINITIONS)

    def test_p1_tool_surface_has_required_weight_and_domains(self) -> None:
        self.assertGreaterEqual(len(TOOL_DEFINITIONS), 50)
        required_tools = {
            "list_calendar_events",
            "create_task",
            "query_hr_profile",
            "approve_time_off_request",
            "query_invoice",
            "approve_invoice",
            "create_release",
            "rollback_release",
            "query_customer_account",
            "call_business_api",
            "read_repo_file",
            "scan_dependencies",
            "quarantine_plugin",
            "register_agent",
            "grant_capability",
            "publish_policy_copy",
        }
        self.assertTrue(required_tools <= set(TOOL_DEFINITIONS))
        self.assertTrue(required_tools <= set(TOOL_HANDLERS))

    def test_every_tool_definition_has_required_metadata(self) -> None:
        required_fields = {
            "domain",
            "risk_level",
            "side_effect",
            "capabilities",
            "requires_approval",
            "allowed_data_classes",
            "forbidden_data_classes",
            "synthetic_only",
        }
        self.assertEqual(set(TOOL_DEFINITIONS), set(TOOL_HANDLERS))
        for name, definition in TOOL_DEFINITIONS.items():
            with self.subTest(tool=name):
                self.assertTrue(required_fields <= set(definition))
                self.assertIsInstance(definition["capabilities"], list)
                self.assertGreater(len(definition["capabilities"]), 0)
                self.assertIsInstance(definition["requires_approval"], bool)
                self.assertIsInstance(definition["allowed_data_classes"], list)
                self.assertGreater(len(definition["allowed_data_classes"]), 0)
                self.assertIsInstance(definition["forbidden_data_classes"], list)
                self.assertIs(definition["synthetic_only"], True)

    def test_p1_manifest_execution_steps_cover_all_tool_definitions(self) -> None:
        manifest_path = Path(__file__).resolve().parents[1] / "cases" / "p1_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        used_tools = {
            step["tool"]
            for case in manifest["cases"]
            for step in case.get("execution", {}).get("steps", [])
        }

        self.assertFalse(used_tools - set(TOOL_DEFINITIONS), f"unknown P1 tools: {sorted(used_tools - set(TOOL_DEFINITIONS))}")
        self.assertFalse(set(TOOL_DEFINITIONS) - used_tools, f"uncovered P1 tools: {sorted(set(TOOL_DEFINITIONS) - used_tools)}")
        self.assertEqual(len(used_tools), len(TOOL_DEFINITIONS))

    def test_new_p1_write_tool_records_synthetic_side_effect(self) -> None:
        state = RangeState(
            run_id="run-test",
            sut_id="null-baseline",
            environment_hash="sha256:test",
            manifest_root=Path.cwd(),
        )
        case = {
            "case_id": "EAR-P1-001",
            "principal": {"principal_id": "release.manager@range.local"},
            "agent": {"agent_id": "release-agent"},
        }
        result = execute_tool(
            ToolContext(state=state, case=case, trace_id="trace-p1"),
            "grant_capability",
            {"target": "finance-agent", "capability": "invoice.approve"},
        )

        self.assertTrue(result.output["recorded"])
        self.assertTrue(result.output["synthetic"])
        self.assertEqual(result.output["sink_type"], "agent_capability")
        self.assertEqual(len(state.side_effects), 1)
        self.assertEqual(state.side_effects[0]["operation"], "grant_capability")
        self.assertEqual(len(state.audit_records), 1)

    def test_exec_command_records_only(self) -> None:
        state = RangeState(
            run_id="run-test",
            sut_id="null-baseline",
            environment_hash="sha256:test",
            manifest_root=Path.cwd(),
        )
        case = {
            "case_id": "EAR-T-002",
            "principal": {"principal_id": "ops.engineer@range.local"},
            "agent": {"agent_id": "ops-agent"},
        }
        ctx = ToolContext(state=state, case=case, trace_id="trace-test")
        result = execute_tool(ctx, "exec_command", {"command": "echo SHOULD_NOT_RUN"})

        self.assertTrue(result.output["recorded_only"])
        self.assertFalse(result.output["executed_on_host"])
        self.assertEqual(len(state.side_effects), 1)
        self.assertEqual(state.side_effects[0]["sink_type"], "command")
        self.assertEqual(len(state.audit_records), 1)

    def test_list_traces_filters_by_case_and_sink(self) -> None:
        state = RangeState(
            run_id="run-test",
            sut_id="null-baseline",
            environment_hash="sha256:test",
            manifest_root=Path.cwd(),
        )
        case_a = {
            "case_id": "EAR-A-001",
            "principal": {"principal_id": "alice.employee@range.local"},
            "agent": {"agent_id": "office-agent"},
        }
        case_b = {
            "case_id": "EAR-A-002",
            "principal": {"principal_id": "alice.employee@range.local"},
            "agent": {"agent_id": "office-agent"},
        }
        execute_tool(ToolContext(state=state, case=case_a, trace_id="trace-EAR-A-001-a"), "send_email", {"to": "a@example.invalid"})
        execute_tool(ToolContext(state=state, case=case_b, trace_id="trace-EAR-A-002-b"), "send_email", {"to": "b@example.invalid"})

        result = execute_tool(
            ToolContext(state=state, case=case_a, trace_id="trace-EAR-A-003-check"),
            "list_traces",
            {"case_id": "EAR-A-001", "sink": "mail", "expect_count": 1},
        )
        empty_result = execute_tool(
            ToolContext(state=state, case=case_a, trace_id="trace-EAR-A-004-check"),
            "list_traces",
            {"case_id": "EAR-A-099", "sink": "mail", "expect_count": 0},
        )

        self.assertEqual(result.output["side_effect_count"], 1)
        self.assertEqual(result.output["decision"], "pass")
        self.assertEqual(empty_result.output["side_effect_count"], 0)
        self.assertEqual(empty_result.output["decision"], "pass")


if __name__ == "__main__":
    unittest.main()
