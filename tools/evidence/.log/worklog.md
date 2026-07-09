# tools/evidence 工作日志

## 2026-07-09
落地 EVIDENCE-LAYOUT-SPEC §6 契约四脚本 + common.sh（POSIX sh，Linux 与 Git Bash 通用）。new-run 建 run 骨架并写 meta.json 初值；seal-run 重算 artifact-hashes（沿用 R8 格式）、确定性 tar+gzip -n、追加 HOST-INDEX 并打印 §4 manifest 行；verify-run 核对 artifact-hashes 与已提交 manifest（git 为唯一信任锚）；collect 拉取 runs/（live）或 sealed/ 并逐包对已提交 manifest 校验，rsync 缺失时给 --scp 降级。seal 前强制 RESULTS.md 首行与 --result 一致，已封存包拒绝覆盖。
