# XA-Guard Kind HA acceptance profile

This profile exercises the Helm HA and rollback path without pretending that
reference dependencies are production in-cluster services. Keycloak 26.7.0,
PostgreSQL 17.6, and the reference HTTP key provider run in Docker Compose
outside Kind. XA-Guard API and Worker run as two replicas inside Kind.

Pinned infrastructure:

- Kind `v0.31.0`;
- Kubernetes node `v1.34.3` with the release-published image digest;
- one control-plane and two worker nodes;
- the default CNI disabled and Calico `v3.32.1` installed from a verified
  manifest;
- Helm `v3.17.3` and kubectl `v1.34.3`.

`tools.lock.json` contains official URLs and SHA-256 values. The bootstrap never
executes an artifact before its checksum passes.

## Bootstrap

Docker must be running. On Docker Desktop, the safe default external bind
address `127.0.0.1` is reachable through `host.docker.internal`. Native Linux
Docker may require an explicitly selected host bridge address; do not use
`0.0.0.0` on a shared or untrusted network.

```bash
python deploy/kind/bootstrap_tools.py
python deploy/kind/ha_runner.py bootstrap
```

Bootstrap performs these operations:

1. generates reference credentials under the already-gitignored
   `.runtime/reference/` and a KMS API token under `.runtime/kind-ha/`;
2. starts `docker-compose.ha-external.yml`;
3. creates the three-node cluster from `cluster.yaml`;
4. installs the checksum-verified Calico manifest;
5. resolves the Docker host, installs a CoreDNS mapping for
   `host.docker.internal`, and writes `values.generated.yaml`;
6. creates the three pre-existing Kubernetes Secrets expected by the chart.

The generated values contain endpoint topology, the selected Docker host
`/32`, and any narrowly scoped external dependency network CIDR needed after
Docker DNAT; they never contain credentials. CIDRs broader than IPv4 `/16` or
IPv6 `/64` are rejected. Generated values are deliberately ignored by
`deploy/kind/.gitignore`.

Use `--host-cidr 172.18.0.1/32` when automatic host-gateway discovery is not
appropriate. Port overrides must be supplied consistently to the runner.

## HA and rollback runner

Build or pull both application revisions and the Console image before running:

```bash
python deploy/kind/ha_runner.py accept \
  --previous-image xa-guard-reference:0.2.0-n-1 \
  --current-image xa-guard-reference:0.2.0 \
  --console-image xa-guard-console:0.2.0 \
  --prepare-takeover
```

Both application images must implement the chart 0.2 health and key-provider
contract; `0.2.0-n-1` denotes the prior compatible candidate, not a legacy image
without Worker HTTP readiness. `--prepare-takeover` creates a real ticket as
Alice, requests Undo, and approves it as Dora after arming a delayed
post-commit response. Tokens stay in memory and are never recorded. An existing
`eff-<32-lowercase-hex>` may instead be supplied with
`--takeover-effect-id`. The runner installs N-1, upgrades to N, reruns the
numbered migration, deletes one API Pod, deletes the Worker holding the lease,
verifies a second Worker completed it, probes allowed and denied network paths,
rolls Helm back, and checks that the prior images and effect state remain
readable.

If neither takeover option is supplied, the evidence is marked `INCOMPLETE`
and the command exits 2. `--allow-incomplete` exists only for
command-plan/static smokes; its output is not HA evidence. Inspect the
non-mutating plan with:

```bash
python deploy/kind/ha_runner.py accept --dry-run --allow-incomplete
```

Evidence is written below the gitignored `deploy/kind/evidence/`. The clean
2026-07-16 run completed every required phase and is committed as
`docs/evidence/agent-identity-undo-acceptance-2026-07-16/acceptance/ha-final-clean-20260716.json`.
It proves this local Kind profile, not production HA: the external OIDC,
PostgreSQL, and key provider were the reference Compose services.

## Cleanup

```bash
python deploy/kind/ha_runner.py destroy
```

Cleanup does not pass `docker compose down -v`; the external PostgreSQL volume
is retained so rollback and migration evidence is not accidentally destroyed.
