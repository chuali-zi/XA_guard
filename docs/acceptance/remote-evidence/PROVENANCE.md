# 证据 Provenance 台账（信任锚）

> 本文件与同目录 `provenance-manifest.jsonl` 是**所有已封存 run 的信任锚**。
> 规则见 [`EVIDENCE-LAYOUT-SPEC.md`](./EVIDENCE-LAYOUT-SPEC.md) §4。
> 一个被采集回来的 `<run-id>.tar.gz` 是真实的，当且仅当其 sha256 等于本表（及 `provenance-manifest.jsonl`）中记录的 `tarball_sha256`。
> 每封存一个 run，追加一行并 commit + push；提交后 git 历史 + 远端即为信任来源。tarball 旁的 `.sha256` 只是便捷校验值，不作准。

| run_id | host | target | end_utc | tarball_sha256 | files | bytes | result |
|---|---|---|---|---|---:|---:|---|
| _（尚无已封存 run）_ | | | | | | | |
