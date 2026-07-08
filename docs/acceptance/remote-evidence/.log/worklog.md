# worklog — remote-evidence

## 2026-07-08
落实证据落盘与 provenance 规范（brainstorming 定案）。冻结固定根：Linux `~/xa-evidence/`、本地 `D:/xa-evidence/`；run 目录标准 layout（meta/environment/commands/console/RESULTS/artifacts/artifact-hashes）；run-id=`<target>-<UTCstamp>-<shorthost>`。封存 seal-run 产 `sealed/<run-id>.tar.gz`+`.sha256`。信任锚采用 git 提交的 `provenance-manifest.jsonl`+`PROVENANCE.md`（非包旁哈希），闭合 status.md BLOCKED #7 本地⇄远端绑定。采集 rsync live + sealed 校验。旧证据 grandfather 不迁移。tools/evidence 脚本仅定义契约待实现。
