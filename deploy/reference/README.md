# XA-Guard reference environment

The reference environment is local-only and uses generated credentials. Start it with:

```bash
python scripts/reference_stack.py up
```

The command creates `.runtime/reference/` (gitignored), renders the Keycloak realm,
mounts credentials as Docker secrets, runs PostgreSQL migrations and idempotent
assignment seeding, then starts Keycloak, XA-Guard control API, the compensation
worker, the stateful ticket API, and the Console/BFF. All host ports bind to
`127.0.0.1`; the ticket API remains internal to the business/data networks.
Use TLS and external secret management for remote environments.

Protocol-level two-person acceptance (without printing or persisting tokens):

```bash
python scripts/verify_reference_e2e.py
```

This uses real Authorization Code + PKCE for Alice and Dora, the Console/BFF
token exchange, a PostgreSQL Effect, an independent approval, and Worker
compensation. Interactive browser visual QA is still a separate manual step.

`python scripts/reference_stack.py credentials` prints the local Alice, Dora,
governance admin, and Keycloak bootstrap credentials. `down` stops services but
keeps PostgreSQL data; `docker compose -f docker-compose.reference.yml down -v`
is the explicit destructive reset.

The pinned reference infrastructure is Keycloak 26.7.0 (Apache-2.0) and
PostgreSQL 17.6 (PostgreSQL License). The Python application is Apache-2.0 and
uses asyncpg (Apache-2.0), Starlette (BSD-3-Clause), HTTPX (BSD-3-Clause),
PyJWT (MIT), and cryptography (Apache-2.0/BSD). Console dependency licenses are
documented in `console/README.md`.

This Compose profile is a reproducible reference, not a production TLS or KMS
deployment. The Helm chart defaults to external OIDC, PostgreSQL, and key
providers.
