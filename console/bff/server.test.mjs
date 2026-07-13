import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { loadConfig, readSecret } from "./config.mjs";
import { createApp } from "./server.mjs";

test("client secret prefers _FILE and trims trailing newline", () => {
  const dir = mkdtempSync(join(tmpdir(), "xa-console-"));
  const path = join(dir, "client-secret");
  writeFileSync(path, "from-file\n", "utf8");
  assert.equal(readSecret("OIDC_CLIENT_SECRET", { OIDC_CLIENT_SECRET: "from-env", OIDC_CLIENT_SECRET_FILE: path }), "from-file");
});

test("Compose-compatible KEYCLOAK and CONTROL_API variables load in explicit reference production", () => {
  const value = loadConfig({
    NODE_ENV: "production",
    KEYCLOAK_URL: "http://keycloak:8080",
    KEYCLOAK_PUBLIC_URL: "http://localhost:13081",
    KEYCLOAK_REALM: "xa-guard",
    KEYCLOAK_CLIENT_ID: "xa-bff",
    KEYCLOAK_CLIENT_SECRET: "compose-secret",
    CONTROL_API_URL: "http://control-api:8080",
  });
  assert.equal(value.issuer, "http://keycloak:8080/realms/xa-guard");
  assert.equal(value.publicIssuer, "http://localhost:13081/realms/xa-guard");
  assert.equal(value.clientId, "xa-bff");
  assert.equal(value.controlApiBaseUrl, "http://control-api:8080");
});

test("production rejects non-reference remote HTTP issuer", () => {
  assert.throws(() => loadConfig({
    NODE_ENV: "production",
    OIDC_ISSUER: "http://id.example.test/realms/xa",
    OIDC_CLIENT_SECRET: "secret",
  }), /must use HTTPS/);
});

test("BFF exchanges human token, proxies agent token, and never returns it", async (t) => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url: String(url), options });
    if (String(url).endsWith("/token")) return Response.json({ access_token: "agent-token-must-stay-server-side" });
    return Response.json({ ok: true, effect_id: "eff-1" }, { headers: { "x-internal-token": "ignored" } });
  };
  const app = createApp({
    issuer: "https://id.example.test/realms/xa",
    tokenEndpoint: "https://id.example.test/token",
    clientId: "xa-bff",
    clientSecret: "bff-secret",
    controlApiBaseUrl: "http://control.internal:3000",
    staticDir: join(tmpdir(), "xa-no-static"),
  }, { fetchImpl });
  const server = app.listen(0, "127.0.0.1");
  t.after(() => server.close());
  await new Promise((resolve) => server.once("listening", resolve));
  const { port } = server.address();
  const response = await fetch(`http://127.0.0.1:${port}/control/v1/effects?status=available`, {
    headers: { authorization: "Bearer human-token", "x-agent-id": "general-office-agent" },
  });
  const body = await response.text();
  assert.equal(response.status, 200);
  assert.equal(calls.length, 2);
  assert.match(String(calls[0].options.body), /subject_token=human-token/);
  assert.match(String(calls[0].options.body), /audience=general-office-agent/);
  assert.equal(calls[1].options.headers.get("authorization"), "Bearer agent-token-must-stay-server-side");
  assert.doesNotMatch(body, /agent-token-must-stay-server-side|human-token|bff-secret/);
});

test("BFF rejects missing bearer before contacting the identity provider", async (t) => {
  let called = false;
  const app = createApp({
    issuer: "https://id.example.test/realms/xa",
    tokenEndpoint: "https://id.example.test/token",
    clientId: "xa-bff",
    clientSecret: "bff-secret",
    controlApiBaseUrl: "http://control.internal:3000",
    staticDir: join(tmpdir(), "xa-no-static"),
  }, { fetchImpl: async () => { called = true; throw new Error("must not run"); } });
  const server = app.listen(0, "127.0.0.1");
  t.after(() => server.close());
  await new Promise((resolve) => server.once("listening", resolve));
  const { port } = server.address();
  const response = await fetch(`http://127.0.0.1:${port}/control/v1/me`, { headers: { "x-agent-id": "general-office-agent" } });
  assert.equal(response.status, 401);
  assert.equal(called, false);
});
