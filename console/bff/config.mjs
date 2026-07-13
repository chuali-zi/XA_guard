import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export function readSecret(name, env = process.env) {
  const file = env[`${name}_FILE`];
  if (file) {
    const value = readFileSync(resolve(file), "utf8").trim();
    if (!value) throw new Error(`${name}_FILE points to an empty file`);
    return value;
  }
  const value = String(env[name] || "").trim();
  if (!value) throw new Error(`${name} or ${name}_FILE is required`);
  return value;
}

function readFirstSecret(names, env) {
  for (const name of names) {
    if (env[name] || env[`${name}_FILE`]) return readSecret(name, env);
  }
  throw new Error(`${names.map((name) => `${name} or ${name}_FILE`).join(", ")} is required`);
}

function normalizedUrl(value, name) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`${name} must be an absolute URL`);
  }
  return url.toString().replace(/\/$/, "");
}

export function loadConfig(env = process.env) {
  const keycloakBase = String(env.KEYCLOAK_URL || env.KEYCLOAK_BASE_URL || "").replace(/\/$/, "");
  const keycloakRealm = String(env.KEYCLOAK_REALM || "xa-guard");
  const issuer = normalizedUrl(
    env.OIDC_ISSUER || env.XA_GUARD_OIDC_ISSUER || env.KEYCLOAK_ISSUER ||
      (keycloakBase ? `${keycloakBase}/realms/${keycloakRealm}` : ""),
    "OIDC_ISSUER",
  );
  const issuerUrl = new URL(issuer);
  const publicBase = String(env.KEYCLOAK_PUBLIC_URL || "").replace(/\/$/, "");
  const publicIssuer = normalizedUrl(
    env.OIDC_PUBLIC_ISSUER || (publicBase ? `${publicBase}/realms/${keycloakRealm}` : issuer),
    "OIDC_PUBLIC_ISSUER",
  );
  const explicitReference = String(env.REFERENCE_INFRA_ENABLED || "").toLowerCase() === "true" ||
    String(env.XA_GUARD_REFERENCE_MODE || "").toLowerCase() === "true" ||
    String(env.XA_GUARD_DEPLOYMENT_PROFILE || "").toLowerCase() === "reference" ||
    String(env.XA_GUARD_PROFILE || "").toLowerCase().includes("reference");
  const loopback = ["localhost", "127.0.0.1", "::1"].includes(issuerUrl.hostname);
  const internalKeycloak = issuerUrl.hostname === "keycloak" || issuerUrl.hostname.endsWith(".svc") || issuerUrl.hostname.endsWith(".cluster.local");
  const referenceComposeKeycloak = Boolean(keycloakBase) && issuerUrl.hostname === "keycloak";
  if ((env.NODE_ENV || "development") === "production" && issuerUrl.protocol !== "https:" && !(loopback || referenceComposeKeycloak || (explicitReference && internalKeycloak))) {
    throw new Error("OIDC_ISSUER must use HTTPS; HTTP is limited to loopback or explicit reference-infra Keycloak");
  }
  return {
    port: Number(env.PORT || 8080),
    issuer,
    publicIssuer,
    tokenEndpoint: normalizedUrl(
      env.OIDC_TOKEN_ENDPOINT || env.KEYCLOAK_TOKEN_ENDPOINT || `${issuer}/protocol/openid-connect/token`,
      "OIDC_TOKEN_ENDPOINT",
    ),
    clientId: String(env.OIDC_CONFIDENTIAL_CLIENT_ID || env.KEYCLOAK_BFF_CLIENT_ID || env.KEYCLOAK_CLIENT_ID || "xa-guard-bff"),
    clientSecret: readFirstSecret(["OIDC_CLIENT_SECRET", "KEYCLOAK_CLIENT_SECRET"], env),
    exchangeAudience: String(env.OIDC_EXCHANGE_AUDIENCE || env.XA_GUARD_OIDC_AUDIENCE || "xa-guard-api"),
    controlApiBaseUrl: normalizedUrl(env.CONTROL_API_BASE_URL || env.CONTROL_API_URL || "http://127.0.0.1:3000", "CONTROL_API_BASE_URL"),
    staticDir: resolve(env.STATIC_DIR || "dist"),
  };
}
