import Keycloak, { type KeycloakTokenParsed } from "keycloak-js";
import type { PublicConfig } from "./types";

export interface IdentitySession {
  username: string;
  subject: string;
  parsed: KeycloakTokenParsed;
  getToken: () => Promise<string>;
  logout: () => Promise<void>;
}

let initialization: Promise<IdentitySession> | undefined;

function keycloakCoordinates(issuer: string) {
  const marker = "/realms/";
  const index = issuer.lastIndexOf(marker);
  if (index < 0) throw new Error("OIDC issuer must contain a Keycloak /realms/{realm} path");
  return { url: issuer.slice(0, index), realm: issuer.slice(index + marker.length).replace(/\/$/, "") };
}

export async function loadPublicConfig(): Promise<PublicConfig> {
  const response = await fetch("/config/config.json", { cache: "no-store", credentials: "omit" });
  if (!response.ok) throw new Error("public console configuration is unavailable");
  const config = await response.json() as PublicConfig;
  if (!config.oidcIssuer || !config.oidcClientId || config.tokenStorage !== "memory") {
    throw new Error("console configuration must use memory-only token storage");
  }
  return config;
}

export function initializeIdentity(config: PublicConfig): Promise<IdentitySession> {
  if (initialization) return initialization;
  initialization = (async () => {
    const coordinates = keycloakCoordinates(config.oidcIssuer);
    const keycloak = new Keycloak({ ...coordinates, clientId: config.oidcClientId });
    const authenticated = await keycloak.init({
      onLoad: "login-required",
      pkceMethod: "S256",
      checkLoginIframe: false,
      flow: "standard",
    });
    if (!authenticated || !keycloak.token || !keycloak.tokenParsed) throw new Error("identity login did not produce a token");

    // keycloak-js keeps access/refresh tokens on this in-memory instance. The
    // application never serializes them to browser storage or application state.
    const getToken = async () => {
      await keycloak.updateToken(30);
      if (!keycloak.token) throw new Error("identity session expired");
      return keycloak.token;
    };
    keycloak.onTokenExpired = () => { void keycloak.updateToken(30); };
    return {
      username: String(keycloak.tokenParsed.preferred_username || keycloak.tokenParsed.sub || "unknown"),
      subject: String(keycloak.tokenParsed.sub || ""),
      parsed: keycloak.tokenParsed,
      getToken,
      logout: () => keycloak.logout({ redirectUri: window.location.origin }),
    };
  })();
  return initialization;
}

