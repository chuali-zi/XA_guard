# remote-evidence —— 证据落盘与采集规范目录

本目录承载“本地 + Linux 远端统一证据规范”及其信任锚。

- [`EVIDENCE-LAYOUT-SPEC.md`](./EVIDENCE-LAYOUT-SPEC.md) —— 规范正文：固定根目录、run 目录标准 layout、封存步骤、git 锚定的 provenance、采集与收束流程。
- [`PROVENANCE.md`](./PROVENANCE.md) —— 人读 provenance 台账（信任锚）。
- `provenance-manifest.jsonl` —— 机器可读 provenance manifest（每封存一 run 追加一行）。
- [`../EVIDENCE-CONSOLIDATION.md`](../EVIDENCE-CONSOLIDATION.md) —— 全部证据的交付映射、校验结果和发布边界。

固定根：Linux 远端 `~/xa-evidence/`，本地 Windows `D:/xa-evidence/`（远端采集镜像落 `D:/xa-evidence/remote/<host>/`）。

当前 provenance 包含 R6 system/rootless 远端证据和 OAR Delivery v2 canonical 本地证据。记录只有 commit + push 后才形成远端 git 信任锚。
