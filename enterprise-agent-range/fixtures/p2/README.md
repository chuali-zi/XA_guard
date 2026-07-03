# P2 fixtures (placeholder)

This directory reserves the home for **P2 synthetic fixtures**. It is empty on
purpose during the scaffold phase — no P2 case data exists yet.

When P2 capabilities are implemented, fixtures land here grouped by capability,
e.g.:

```text
fixtures/p2/
├── tenancy/        # multi-tenant org/data samples
├── discovery/      # shadow-AI inventory & trace samples
├── identity/       # agent identity lifecycle samples
├── permissions/    # JIT/JEA/JLA grant request samples
├── risk/           # risk-scoring inputs
├── remediation/    # committed-effect samples for undo planning
├── benchmark/      # OFFLINE external benchmark exports only
└── evidence/       # mock TSA/HSM tokens
```

Rules (inherited from `docs/architecture/decoupling-contract.md` and
`docs/architecture/decoupling-contract.md`):

- Synthetic data only — no real PII, secrets, or production exports.
- Offline only — no live third-party benchmark/TSA/HSM calls.
- Referenced by manifests via relative paths under the range root.
