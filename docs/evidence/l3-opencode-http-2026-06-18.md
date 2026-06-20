# OpenCode real LLM to Streamable HTTP MCP evidence

Date: 2026-06-18 (Asia/Shanghai)

## Scope

This is a real OpenCode 1.17.8 / GLM-5.2 client run against the stateful
XA-Guard Streamable HTTP endpoint. It proves one LLM-selected allow call over
HTTP MCP; it is not a multi-client load test or a Trae UI claim.

Profiles:

- XA-Guard: `configs/xa-guard.opencode-http.yaml`
- OpenCode: `configs/opencode.l3-http.json`
- Endpoint: `http://127.0.0.1:18765/mcp`
- Model: `opencode-go/glm-5.2`

The OpenCode process ran from an isolated temporary directory so the root
stdio `opencode.json` could not be merged. `NO_PROXY` and `no_proxy` were set
to `127.0.0.1,localhost` because the host has a system HTTP proxy.

## Observed result

`opencode.cmd mcp list` reported only:

```text
xa_guard_l3_http connected
http://127.0.0.1:18765/mcp
```

The JSON event stream contained:

```json
{"type":"tool_use","tool":"xa_guard_l3_http_get_cpu","input":{"host":"web03"},"output":"{\"host\": \"web03\", \"cpu\": \"85%\"}"}
```

The model then reported `host=web03, cpu=85%`. Uvicorn recorded MCP
initialization and call traffic (`POST /mcp` 200/202 plus `GET /mcp` 200).
The service was stopped after the run and port 18765 had no listener.

## Audit verification

- trace ID: `cf2f194f-087a-4ad7-884c-dac817c3b763`
- record hash: `ce65510436a37576865740068e00c60a8ff2a4fff424b97ac0262a3bbb192de6`
- tool/arguments: `get_cpu`, `{"host":"web03"}`
- decision: `allow`
- verifier: `1 records, 0 chain/hash errors, 0 JSON parse errors, 0 missing-field records`
- copied audit: `docs/evidence/l3-opencode-http-audit-2026-06-18.jsonl`

An initial attempt was rejected as evidence: OpenCode inherited the system
proxy, the HTTP MCP showed a 502, and OpenCode fell back to the repository's
stdio server. The successful run above removed both confounders before the
model call.
