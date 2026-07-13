# worklog — remote-evidence

## 2026-07-11
从远端 `ubuntu-test` 回传 `/home/ubuntu/xa-evidence` 到本地规范镜像 `D:/xa-evidence/remote/ubuntu-test/`。共 13 个目录、158 个文件、782683 bytes；端到端 SHA-256 比对 0 缺失、0 额外、0 不一致。两个 sealed 包写入 provenance：system runsc PASS，rootless runsc LIMIT。未提交/推送。

同日新增 OAR canonical sealed run：127 files / 451499 bytes，tar SHA-256 `cffa89fb...49aa5`，run/artifact/tarball 校验通过并写入 provenance。记录仍需 commit+push 才成为远端信任锚。

## 2026-07-08
落实证据落盘与 provenance 规范（brainstorming 定案）。冻结固定根：Linux `~/xa-evidence/`、本地 `D:/xa-evidence/`；run 目录标准 layout（meta/environment/commands/console/RESULTS/artifacts/artifact-hashes）；run-id=`<target>-<UTCstamp>-<shorthost>`。封存 seal-run 产 `sealed/<run-id>.tar.gz`+`.sha256`。信任锚采用 git 提交的 `provenance-manifest.jsonl`+`PROVENANCE.md`（非包旁哈希），闭合 status.md BLOCKED #7 本地⇄远端绑定。采集 rsync live + sealed 校验。旧证据 grandfather 不迁移。tools/evidence 脚本仅定义契约待实现。
