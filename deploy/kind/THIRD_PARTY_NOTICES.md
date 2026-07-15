# HA deployment tooling notices

No third-party binary or Calico manifest is committed in this directory. The
checksum bootstrap downloads the following upstream artifacts into the
gitignored `.tools/` directory:

| Component | Version | License | Upstream |
|---|---:|---|---|
| kind | v0.31.0 | Apache-2.0 | https://github.com/kubernetes-sigs/kind |
| Kubernetes / kubectl / kindest-node | v1.34.3 | Apache-2.0 | https://github.com/kubernetes/kubernetes |
| Helm | v3.17.3 | Apache-2.0 | https://github.com/helm/helm |
| Calico | v3.32.1 | Apache-2.0 | https://github.com/projectcalico/calico |
| Keycloak | 26.7.0 | Apache-2.0 | https://github.com/keycloak/keycloak |
| PostgreSQL | 17.6 | PostgreSQL License | https://www.postgresql.org/ |

The exact download URLs and SHA-256 values are recorded in `tools.lock.json`;
container image digests are recorded in `cluster.yaml` and
`docker-compose.ha-external.yml`. Operators remain responsible for reviewing
their organization's image registry, export-control, vulnerability, and license
policies before production use.
