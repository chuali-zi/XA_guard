# Control module work log

## 2026-07-19 OpenCode
- Added completion CAS metadata, ordered prepared/Event inserts, pool tuning, and migration 006 for lock-then-tail reads with fresh PostgreSQL snapshots.
- Rejected unsafe one-statement tail reads and regressing size-triggered/2.5ms batch experiments.
- Ruff and 40 control tests pass. Safe 3x500 candidate still fails the 50ms threshold; next step is a unified mixed Effect mutation queue.

## 2026-07-20 OpenCode
- Added opt-in reference timing for the ticket write path and cached Gate2 legacy risk data.
- Added covering tenant-chain tail indexes; no audit, intent-first, or cross-replica lock semantics changed.
- Formal performance evidence remains unchanged pending a qualifying rerun.
