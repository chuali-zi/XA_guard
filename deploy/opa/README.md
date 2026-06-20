# OPA/Rego deployment profile

This optional Compose override installs the OPA CLI from the official
`openpolicyagent/opa` image and starts XA-Guard with
`configs/xa-guard.opa.yaml`. Gate3 uses `backend: rego`,
`strict_opa: true`, and `/usr/local/bin/opa`; a missing executable therefore
fails startup instead of silently selecting the Python evaluator.

OPA is Apache-2.0 licensed. XA-Guard does not commit a downloaded OPA binary.
The deployment operator must pin `XA_GUARD_OPA_IMAGE` to an approved immutable
digest and archive the image digest, OPA version output, license/NOTICE, and
vulnerability scan. The default versioned tag is a build template, not a
production provenance claim.

Static validation:

```sh
docker compose -f docker-compose.yml -f deploy/opa/docker-compose.opa.yml config
python scripts/verify_l3_static.py --section opa
```

Later runtime acceptance:

1. Set `XA_GUARD_OPA_IMAGE=openpolicyagent/opa:1.4.2-static@sha256:<approved>`.
2. Build and start the merged profile.
3. Verify `opa version` inside the service and health endpoint readiness.
4. Run the same allow/deny policy fixtures against Python and strict OPA
   profiles; normalized decisions and rule-hit sets must match 100%.
5. Remove or rename `/usr/local/bin/opa`; startup must fail closed.
6. Archive effective Compose config, image digest, fixture report, audit chain,
   and performance comparison.

No OPA runtime or performance result is claimed by the static repository check.
