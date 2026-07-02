from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.systems import RangeState, ToolContext
from enterprise_agent_range.tools import TOOL_DEFINITIONS, execute_tool


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
