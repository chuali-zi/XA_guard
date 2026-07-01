from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import subprocess

import pytest
from bench.external.injecagent_opencode import OpenCodeReActModel
from bench.external.agentdojo_opencode import normalize_text_content

from bench.external.opencode_bridge import (
    ProviderQuotaPaused,
    budget_bucket_for_attempt,
    invoke_opencode_json,
    parse_opencode_json_events,
)
from bench.external.budget import create_ledger, load_ledger, ledger_totals


def _event(event_type: str, **part):
    return json.dumps({"type": event_type, "part": part})


def test_parse_opencode_json_events_returns_last_text_object():
    stdout = "\n".join(
        [
            _event("step_start"),
            _event("text", text='{"content":null,"tool_calls":[]}'),
            _event("step_finish"),
        ]
    )

    assert parse_opencode_json_events(stdout) == {
        "content": None,
        "tool_calls": [],
    }


def test_parse_opencode_json_events_accepts_fenced_json():
    stdout = _event("text", text='```json\n{"content":"done","tool_calls":[]}\n```')

    assert parse_opencode_json_events(stdout)["content"] == "done"


def test_parse_opencode_json_events_extracts_fenced_json_after_preamble():
    fence = chr(96) * 3
    stdout = _event(
        "text",
        text=(
            "I will call the date tool first.\n\n"
            + fence
            + 'json\n{"content":null,"tool_calls":[{"function":"get_day","args":{}}]}\n'
            + fence
        ),
    )

    assert parse_opencode_json_events(stdout)["tool_calls"][0]["function"] == "get_day"


def test_parse_opencode_json_events_accepts_raw_newline_in_nested_string():
    stdout = _event(
        "text",
        text='{"output":"Thought: inspect\nFinal Answer: done"}',
    )

    assert parse_opencode_json_events(stdout)["output"].endswith(
        "Final Answer: done"
    )



@pytest.mark.parametrize(
    ("filename", "response_source"),
    [("response.json", "temporary_json_file"), ("response.txt", "temporary_response_file")],
)
def test_invoke_opencode_json_uses_temporary_file_fallback(tmp_path, monkeypatch, filename, response_source):
    invocation_log = tmp_path / "invocations.jsonl"

    def fake_run(command, **kwargs):
        del kwargs
        prompt_path = Path(command[-1])
        (prompt_path.parent / filename).write_text(
            json.dumps({"content": "done", "tool_calls": []}),
            encoding="utf-8",
        )
        return SimpleNamespace(
            returncode=0,
            stdout=_event("text", text="Done."),
            stderr="",
        )

    monkeypatch.setattr(
        "bench.external.opencode_bridge.subprocess.run",
        fake_run,
    )

    response = invoke_opencode_json(
        "turn",
        executable="opencode",
        model="test-model",
        cwd=tmp_path / "runtime",
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        timeout_seconds=1,
        invocation_log=invocation_log,
    )

    assert response == {"content": "done", "tool_calls": []}
    record = json.loads(invocation_log.read_text(encoding="utf-8"))
    assert record["response_source"] == response_source
    assert record["parse_error"] == ""


def test_invoke_opencode_json_uses_mutated_prompt_file_fallback(tmp_path, monkeypatch):
    invocation_log = tmp_path / "invocations.jsonl"

    def fake_run(command, **kwargs):
        del kwargs
        Path(command[-1]).write_text(
            json.dumps(
                {
                    "content": None,
                    "tool_calls": [{"function": "send_email", "args": {}}],
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(
            returncode=0,
            stdout=_event("text", text="Done."),
            stderr="",
        )

    monkeypatch.setattr(
        "bench.external.opencode_bridge.subprocess.run",
        fake_run,
    )

    response = invoke_opencode_json(
        "turn",
        executable="opencode",
        model="test-model",
        cwd=tmp_path / "runtime",
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        timeout_seconds=1,

        invocation_log=invocation_log,
    )

    assert response["tool_calls"][0]["function"] == "send_email"
    record = json.loads(invocation_log.read_text(encoding="utf-8"))
    assert record["response_source"] == "mutated_prompt_file"

def test_invoke_opencode_json_logs_timeout_before_raising(tmp_path, monkeypatch):
    invocation_log = tmp_path / "invocations.jsonl"

    def fake_run(command, **kwargs):
        del kwargs
        raise subprocess.TimeoutExpired(
            command,
            timeout=1,
            output="partial output",
            stderr="provider stalled",
        )

    monkeypatch.setattr(
        "bench.external.opencode_bridge.subprocess.run",
        fake_run,
    )

    with pytest.raises(RuntimeError, match="OpenCode exited 124"):
        invoke_opencode_json(
            "turn",
            executable="opencode",
            model="test-model",
            cwd=tmp_path / "runtime",
            config_home=tmp_path / "config",
            data_home=tmp_path / "data",
            timeout_seconds=1,
            invocation_log=invocation_log,
        )

    record = json.loads(invocation_log.read_text(encoding="utf-8"))
    assert record["returncode"] == 124
    assert record["response_source"] == "none"
    assert "timed out after 1 seconds" in record["stderr"]


def test_injecagent_adapter_requests_neutral_react_json(tmp_path, monkeypatch):
    captured = {}

    def fake_invoke(prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        return {"output": "Thought: done\nFinal Answer: safe"}

    monkeypatch.setattr(
        "bench.external.injecagent_opencode.invoke_opencode_json",
        fake_invoke,
    )
    model = OpenCodeReActModel(
        executable="opencode",
        model="test-model",
        cwd=tmp_path / "runtime",
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        invocation_log=tmp_path / "invocations.jsonl",
    )

    model_input = model.prepare_input("system", "user")
    output = model.call_model(model_input)

    assert output == "Thought: done\nFinal Answer: safe"
    assert "SYSTEM PROMPT:\nsystem" in model_input
    assert "USER PROMPT:\nuser" in model_input
    assert "distrust" not in model_input.lower()
    assert "untrusted" not in model_input.lower()
    assert captured["request_message"] == (
        "Return the requested JSON object for the attached InjecAgent turn."
    )

def test_parse_opencode_json_events_rejects_error_event():
    with pytest.raises(RuntimeError, match="OpenCode error event"):
        parse_opencode_json_events(json.dumps({"type": "error", "error": {"message": "no"}}))


def test_agentdojo_adapter_normalizes_text_block_content():
    assert normalize_text_content([
        {"type": "text", "text": "hello"},
        {"type": "text", "text": " world"},
    ]) == "hello world"
    assert normalize_text_content(None) is None
    assert normalize_text_content("plain") == "plain"


def test_agentdojo_adapter_rejects_mixed_content_blocks():
    with pytest.raises(ValueError, match="only text blocks"):
        normalize_text_content([
            {"type": "text", "text": "ok"},
            {"type": "tool_use", "name": "bash"},
        ])


def test_turn_retry_uses_retry_bucket_after_first_attempt():
    assert budget_bucket_for_attempt(1, "calibration", "retry") == "calibration"
    assert budget_bucket_for_attempt(2, "calibration", "retry") == "retry"


def test_injecagent_turn_retry_switches_to_retry_bucket(tmp_path, monkeypatch):
    buckets = []

    def fake_invoke(prompt, **kwargs):
        del prompt
        buckets.append(kwargs["budget_bucket"])
        if len(buckets) == 1:
            raise ValueError("bad JSON")
        return {"output": "Thought: done\nFinal Answer: safe"}

    monkeypatch.setattr("bench.external.injecagent_opencode.invoke_opencode_json", fake_invoke)
    model = OpenCodeReActModel(
        executable="opencode", model="test", cwd=tmp_path,
        budget_bucket="r3_main", retry_budget_bucket="retry", max_turn_retries=2,
    )
    assert model.call_model("turn").endswith("Final Answer: safe")
    assert buckets == ["r3_main", "retry"]


def test_provider_quota_rejection_refunds_reservation_without_halting(tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger.json"
    create_ledger(ledger_path, total_cap_usd=1, caps={"calibration": 1})

    def fake_run(command, **kwargs):
        del command, kwargs
        return SimpleNamespace(returncode=1, stdout="", stderr="quota exceeded for weekly usage limit")

    monkeypatch.setattr("bench.external.opencode_bridge.subprocess.run", fake_run)
    with pytest.raises(ProviderQuotaPaused):
        invoke_opencode_json(
            "turn", executable="opencode", model="test", cwd=tmp_path / "runtime",
            timeout_seconds=1, budget_ledger=ledger_path, budget_bucket="calibration",
            budget_job_id="job", max_invocation_reserve_usd=0.2,
        )
    ledger = load_ledger(ledger_path)
    assert ledger["halted"] is False
    assert ledger_totals(ledger)["total_usd"] == 0.0
    assert ledger["entries"][0]["usage"]["provider_quota_paused"] is True
