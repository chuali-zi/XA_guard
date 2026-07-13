# 证据 Provenance 台账（信任锚）

> 本文件与同目录 `provenance-manifest.jsonl` 是**所有已封存 run 的信任锚**。
> 规则见 [`EVIDENCE-LAYOUT-SPEC.md`](./EVIDENCE-LAYOUT-SPEC.md) §4。
> 一个被采集回来的 `<run-id>.tar.gz` 是真实的，当且仅当其 sha256 等于本表（及 `provenance-manifest.jsonl`）中记录的 `tarball_sha256`。
> 每封存一个 run，追加一行并 commit + push；提交后 git 历史 + 远端即为信任来源。tarball 旁的 `.sha256` 只是便捷校验值，不作准。

| run_id | host | target | end_utc | tarball_sha256 | files | bytes | result |
|---|---|---|---|---|---:|---:|---|
| l3-r6-runsc-20260708T081901Z-ubuntu-test | ubuntu-test | R6-RUNSC-SYSTEM | 2026-07-08T08:19:10Z | 21ec6c6460377294290db6c19b5f98d32cd681c589e4ea58b0c5d4587095e987 | 35 | 148722 | PASS |
| l3-r6-rootless-runsc-20260708T081932Z-ubuntu-test | ubuntu-test | R6-RUNSC-ROOTLESS | 2026-07-08T08:19:33Z | ed63536572244ba7a4788d289b71feada26e9c267326fe0776ed762d96e7571b | 19 | 91857 | LIMIT |
| oar-delivery-v2-20260711T123124Z-win-local | win-local | OAR-DELIVERY-V2 | 2026-07-11T12:32:36Z | cffa89fb2ded79cb17685348bfb6571d85c3c233ad963528ca79b89e2ec49aa5 | 127 | 451499 | PASS |
