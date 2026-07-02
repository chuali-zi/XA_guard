from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import unittest
from unittest import mock
from pathlib import Path
from urllib import request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.protocol import (
    RangeHTTPServer,
    build_protocol_state,
    handle_protocol_request,
    replay_ide_file,
    serve_stdio,
)
from enterprise_agent_range.systems import ToolContext
from enterprise_agent_range.tools import execute_tool


class ProtocolSurfaceTest(unittest.TestCase):
    def _write_fixture_sandbox(self, tmpdir: str) -> tuple[Path, str, str]:
        sandbox = Path(tmpdir)
        manifest_root = sandbox / "range-root"
        policy_dir = manifest_root / "fixtures" / "policies"
        policy_dir.mkdir(parents=True)
        allowed_text = "# Allowed Policy\nSynthetic fixture inside manifest root.\n"
        policy_dir.joinpath("allowed-policy.md").write_text(allowed_text, encoding="utf-8")
        escaped_text = "PARENT_STATUS_SENTINEL: this must never be returned by fixture reads\n"
        sandbox.joinpath("status.md").write_text(escaped_text, encoding="utf-8")
        return manifest_root, allowed_text, escaped_text

    def _guard_parent_status_read(self, manifest_root: Path) -> mock._patch:
        forbidden_path = manifest_root.parent.joinpath("status.md").resolve()
        original_read_text = Path.read_text

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path.resolve() == forbidden_path:
                raise AssertionError("path traversal attempted to read parent status.md")
            return original_read_text(path, *args, **kwargs)

        return mock.patch.object(Path, "read_text", guarded_read_text)

    def test_direct_read_policy_doc_rejects_parent_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_root, _allowed_text, escaped_text = self._write_fixture_sandbox(tmpdir)
            state = build_protocol_state(manifest_root=manifest_root, run_id="direct-traversal-test")
            ctx = ToolContext(
                state=state,
                case={
                    "case_id": "PROTO-TRAVERSAL-DIRECT",
                    "principal": {"principal_id": "tester@range.local"},
                    "agent": {"agent_id": "protocol-test-agent"},
                },
                trace_id="trace-PROTO-TRAVERSAL-DIRECT",
            )

            with self._guard_parent_status_read(manifest_root):
                try:
                    result = execute_tool(ctx, "read_policy_doc", {"fixture_ref": "../status.md"})
                except (PermissionError, ValueError):
                    return

        output_json = json.dumps(result.output, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(escaped_text.strip(), output_json)
        self.assertIn(str(result.output.get("decision")), {"deny", "denied", "invalid", "blocked"})

    def test_protocol_tools_call_rejects_parent_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_root, _allowed_text, escaped_text = self._write_fixture_sandbox(tmpdir)
            state = build_protocol_state(manifest_root=manifest_root, run_id="protocol-traversal-test")

            with self._guard_parent_status_read(manifest_root):
                response = handle_protocol_request(
                    state,
                    {
                        "id": "traversal-call",
                        "method": "tools/call",
                        "params": {
                            "name": "read_policy_doc",
                            "arguments": {"fixture_ref": "../status.md"},
                            "case_id": "PROTO-TRAVERSAL-CALL",
                        },
                    },
                )

        self.assertFalse(response["ok"])
        self.assertEqual(response["id"], "traversal-call")
        self.assertNotIn(escaped_text.strip(), json.dumps(response, ensure_ascii=False, sort_keys=True))

    def test_protocol_read_policy_doc_allows_manifest_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_root, allowed_text, _escaped_text = self._write_fixture_sandbox(tmpdir)
            state = build_protocol_state(manifest_root=manifest_root, run_id="protocol-fixture-test")

            response = handle_protocol_request(
                state,
                {
                    "id": "allowed-call",
                    "method": "tools/call",
                    "params": {
                        "name": "read_policy_doc",
                        "arguments": {"fixture_ref": "fixtures/policies/allowed-policy.md"},
                        "case_id": "PROTO-FIXTURE-CALL",
                    },
                },
            )

        self.assertTrue(response["ok"])
        output = response["result"]["output"]
        self.assertEqual(output["fixture_ref"], "fixtures/policies/allowed-policy.md")
        self.assertEqual(output["content"]["raw"], allowed_text)
        self.assertEqual(output["kind"], "policy_doc")

    def test_protocol_tools_list_and_call(self) -> None:
        state = build_protocol_state(manifest_root=Path.cwd(), run_id="protocol-test")

        tools = handle_protocol_request(state, {"id": "list-1", "method": "tools/list"})
        call = handle_protocol_request(
            state,
            {
                "id": "call-1",
                "method": "tools/call",
                "params": {
                    "name": "send_notification",
                    "arguments": {"channel": "test", "message": "synthetic only"},
                    "case_id": "PROTO-T-001",
                },
            },
        )

        self.assertTrue(tools["ok"])
        self.assertIn("send_notification", tools["result"]["tools"])
        self.assertTrue(call["ok"])
        self.assertEqual(call["result"]["tool_name"], "send_notification")
        self.assertEqual(call["result"]["output"]["sink_type"], "notification")
        self.assertEqual(len(state.side_effects), 1)
        self.assertEqual(len(state.audit_records), 1)

    def test_stdio_json_lines_supports_list_and_call(self) -> None:
        state = build_protocol_state(manifest_root=Path.cwd(), run_id="stdio-test")
        stdin = io.StringIO(
            json.dumps({"id": 1, "method": "tools/list"}) + "\n"
            + json.dumps(
                {
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "get_cpu", "arguments": {"host": "web01"}},
                }
            )
            + "\n"
        )
        stdout = io.StringIO()

        exit_code = serve_stdio(state, stdin=stdin, stdout=stdout)
        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(responses), 2)
        self.assertIn("get_cpu", responses[0]["result"]["tools"])
        self.assertEqual(responses[1]["result"]["output"]["host"], "web01")

    def test_http_health_tools_and_call_are_local(self) -> None:
        state = build_protocol_state(manifest_root=Path.cwd(), run_id="http-test")
        server = RangeHTTPServer(("127.0.0.1", 0), state)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with request.urlopen(f"{base_url}/healthz", timeout=5) as response:
                health = json.loads(response.read().decode("utf-8"))
            with request.urlopen(f"{base_url}/tools", timeout=5) as response:
                tools = json.loads(response.read().decode("utf-8"))

            payload = json.dumps(
                {
                    "name": "submit_change_ticket",
                    "arguments": {"ticket_id": "CHG-PROTO-1", "change_type": "standard"},
                    "case_id": "PROTO-H-001",
                }
            ).encode("utf-8")
            http_request = request.Request(
                f"{base_url}/call",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(http_request, timeout=5) as response:
                call = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertTrue(health["ok"])
        self.assertIn("submit_change_ticket", tools["tools"])
        self.assertTrue(call["ok"])
        self.assertEqual(call["result"]["output"]["ticket_id"], "CHG-PROTO-1")
        self.assertEqual(state.side_effects[0]["sink_type"], "ticket")

    def test_ide_replay_uses_same_tool_call_path(self) -> None:
        state = build_protocol_state(manifest_root=Path.cwd(), run_id="ide-test")
        with tempfile.TemporaryDirectory() as tmpdir:
            replay_path = Path(tmpdir) / "replay.json"
            replay_path.write_text(
                json.dumps(
                    {
                        "calls": [
                            {
                                "name": "query_project",
                                "arguments": {"project_id": "PRJ-PROTO"},
                                "case_id": "PROTO-I-001",
                            },
                            {
                                "name": "export_report",
                                "arguments": {"format": "json", "report": {"ok": True}},
                                "case_id": "PROTO-I-002",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            responses = replay_ide_file(state, replay_path)

        self.assertEqual(len(responses), 2)
        self.assertTrue(all(response["ok"] for response in responses))
        self.assertEqual(responses[0]["result"]["tool_name"], "query_project")
        self.assertEqual(responses[1]["result"]["output"]["sink_type"], "report")
        self.assertEqual(len(state.audit_records), 2)


if __name__ == "__main__":
    unittest.main()
