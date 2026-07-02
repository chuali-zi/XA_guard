from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import unittest
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


class ProtocolSurfaceTest(unittest.TestCase):
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
