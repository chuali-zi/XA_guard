import crypto from "node:crypto";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import express from "express";
import helmet from "helmet";
import { loadConfig } from "./config.mjs";

const AGENT_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const HOP_BY_HOP = new Set(["connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"]);

function bearer(header) {
  const [scheme, token, extra] = String(header || "").trim().split(/\s+/);
  if (scheme?.toLowerCase() !== "bearer" || !token || extra) return "";
  return token;
}

async function exchangeToken(config, humanToken, agentId, fetchImpl) {
  const body = new URLSearchParams({
    grant_type: "urn:ietf:params:oauth:grant-type:token-exchange",
    subject_token: humanToken,
    subject_token_type: "urn:ietf:params:oauth:token-type:access_token",
    requested_token_type: "urn:ietf:params:oauth:token-type:access_token",
    client_id: config.clientId,
    client_secret: config.clientSecret,
    // The confidential Agent client is the token-exchange requester (and
    // therefore becomes azp). The requested audience is the XA-Guard resource
    // server, not the requester client itself.
    audience: config.exchangeAudience || agentId,
  });
  const response = await fetchImpl(config.tokenEndpoint, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded", accept: "application/json" },
    body,
    signal: AbortSignal.timeout(8_000),
  });
  if (!response.ok) throw Object.assign(new Error("identity provider rejected token exchange"), { status: 401 });
  const value = await response.json();
  if (!value?.access_token || typeof value.access_token !== "string") {
    throw Object.assign(new Error("identity provider returned no exchanged access token"), { status: 502 });
  }
  return value.access_token;
}

function safeProxyHeaders(request, agentToken, agentId, traceId) {
  const headers = new Headers();
  for (const [name, value] of Object.entries(request.headers)) {
    const lower = name.toLowerCase();
    if (!value || HOP_BY_HOP.has(lower) || lower === "authorization" || lower === "cookie" || lower === "host" || lower === "content-length") continue;
    headers.set(name, Array.isArray(value) ? value.join(",") : value);
  }
  headers.set("authorization", `Bearer ${agentToken}`);
  headers.set("x-agent-id", agentId);
  headers.set("x-correlation-id", traceId);
  headers.set("accept", "application/json");
  return headers;
}

export function createApp(config, { fetchImpl = fetch } = {}) {
  const app = express();
  app.disable("x-powered-by");
  app.set("trust proxy", 1);
  const idpOrigins = [...new Set([config.issuer, config.publicIssuer || config.issuer].map((value) => new URL(value).origin))];
  app.use(helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        scriptSrc: ["'self'"],
        styleSrc: ["'self'", "'unsafe-inline'"],
        imgSrc: ["'self'", "data:"],
        connectSrc: ["'self'", ...idpOrigins],
        frameSrc: ["'self'", ...idpOrigins],
        objectSrc: ["'none'"],
        baseUri: ["'self'"],
        frameAncestors: ["'none'"],
      },
    },
    referrerPolicy: { policy: "no-referrer" },
  }));
  app.use(express.json({ limit: "512kb", strict: true }));

  app.get("/healthz", (_request, response) => response.json({ status: "ok", token_persistence: "disabled" }));

  app.use("/control/v1", async (request, response) => {
    const traceId = String(request.get("x-correlation-id") || crypto.randomUUID());
    response.set("x-correlation-id", traceId);
    try {
      const humanToken = bearer(request.get("authorization"));
      if (!humanToken) return response.status(401).json({ code: "invalid_token", message: "human bearer token is required", trace_id: traceId });
      const agentId = String(request.get("x-agent-id") || "");
      if (!AGENT_ID.test(agentId)) return response.status(400).json({ code: "invalid_agent", message: "X-Agent-ID is required", trace_id: traceId });

      // Tokens are deliberately request-scoped local variables: no cookie,
      // cache, session, log, response field, or browser-visible exchange body.
      const agentToken = await exchangeToken(config, humanToken, agentId, fetchImpl);
      const suffix = request.originalUrl.replace(/^\/control\/v1/, "");
      const target = `${config.controlApiBaseUrl}/control/v1${suffix}`;
      const headers = safeProxyHeaders(request, agentToken, agentId, traceId);
      const method = request.method.toUpperCase();
      const upstream = await fetchImpl(target, {
        method,
        headers,
        body: ["GET", "HEAD"].includes(method) ? undefined : JSON.stringify(request.body ?? {}),
        signal: AbortSignal.timeout(15_000),
      });
      const contentType = upstream.headers.get("content-type") || "application/json";
      const payload = Buffer.from(await upstream.arrayBuffer());
      response.status(upstream.status).type(contentType).send(payload);
    } catch (error) {
      const status = Number(error?.status || 502);
      response.status(status).json({
        code: status === 401 ? "token_exchange_rejected" : "bff_upstream_unavailable",
        message: status === 401 ? "identity exchange was rejected" : "control service is temporarily unavailable",
        trace_id: traceId,
      });
    }
  });

  if (existsSync(config.staticDir)) {
    app.use(express.static(config.staticDir, { index: false, maxAge: "1h", etag: true }));
    app.get("*splat", (_request, response) => response.sendFile("index.html", { root: config.staticDir }));
  }
  return app;
}

const isEntrypoint = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isEntrypoint) {
  const config = loadConfig();
  createApp(config).listen(config.port, "0.0.0.0", () => {
    console.log(JSON.stringify({ event: "bff_started", port: config.port, token_persistence: "disabled" }));
  });
}
