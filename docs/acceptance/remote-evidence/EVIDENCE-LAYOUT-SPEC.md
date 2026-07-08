# 证据落盘与 Provenance 规范（本地 + Linux 远端统一）

> 冻结日期：2026-07-08。适用范围：**所有后续新证据**（本地与 Linux/远端），包括 L3 远端矩阵 R2/R3、R6 gVisor/runsc、R7 OPA 及未来任意验收/红队证据。
> 目标：把新证据规范在**固定位置**，用统一的 run 目录结构落盘，用**可在 git 中锚定的 provenance manifest** 闭合信任链，便于后续从远端采集回本地并收束成同一次真实验收。
> 本规范只约束**新**证据。旧的分散目录（`docs/evidence/`、`D:/evidence/`、`/mnt/d/evidence/`、`docs/acceptance/*/evidence/`）grandfathered，不迁移，见 §7。

---

## 1. 固定根目录与顶层结构

同一套结构，按平台落在固定根：

- Linux/远端主机：根 = `~/xa-evidence/`
- 本地 Windows：根 = `D:/xa-evidence/`（采集回来的远端证据落在 `D:/xa-evidence/remote/<host>/` 下，见 §5）

顶层结构（每台主机一致）：

```
<root>/
├── runs/                     # 进行中 + 已完成的 run 目录（迭代期 rsync 的目标）
│   └── <run-id>/
├── sealed/                   # 已封存、可采集的打包
│   ├── <run-id>.tar.gz
│   └── <run-id>.tar.gz.sha256
└── HOST-INDEX.jsonl          # 本机 run 的 append-only 本地索引（每 run 一行）
```

`runs/` 用于迭代期实时同步；`sealed/` 是完成后封存的不可变包；`HOST-INDEX.jsonl` 是本机所有 run 的本地台账（不是信任锚，信任锚在 git，见 §4）。

---

## 2. run 目录 —— 证据的标准单元

### 2.1 run-id 命名

```
<target>-<UTCstamp>-<shorthost>
```

- `<target>`：验收/红队标的，如 `l3-r7-opa`、`l3-r6-runsc`、`l3-r2-agentdojo`、`l3-r3-injecagent`。
- `<UTCstamp>`：`YYYYMMDDThhmmssZ`，UTC，紧凑 ISO-8601（与既有 R8 目录 `l3-r8-aibom-20260707T105519Z` 一致）。
- `<shorthost>`：短主机标识（如 `lin01`），保证多台主机的 run 不撞名。

示例：`l3-r7-opa-20260708T143000Z-lin01`。

### 2.2 run 目录内容（标准 layout）

```
<run-id>/
├── meta.json            # 机器可读 provenance（见 2.3）
├── environment.txt      # 人读环境快照：uname -a、发行版、关键工具版本
├── commands.txt         # 本次真实执行的命令，按顺序
├── console.log          # 完整 stdout/stderr 逐字 transcript（script(1) 或 tee 捕获）
├── RESULTS.md           # 人读结论：PASS / LIMIT / BLOCKED + 指标 + 边界声明
├── artifacts/           # 原始产物：json/jsonl 报告、容器日志、trivy/opa 输出等
└── artifact-hashes.json # run 内每个文件的 SHA-256 + bytes（不含自身）
```

该结构是对既有 R8/R4 约定（`environment.txt` / `commands.txt` / `artifact-hashes.json` / `RESULTS.md`）的泛化，不新造格式。

### 2.3 `meta.json` 字段（机器可读 provenance）

```json
{
  "run_id": "l3-r7-opa-20260708T143000Z-lin01",
  "target": "R7-OPA",
  "host": {
    "shorthost": "lin01",
    "fqdn": "lin01.example.internal",
    "os": "Ubuntu 24.04.1 LTS",
    "kernel": "6.8.0-40-generic",
    "arch": "x86_64"
  },
  "git": {
    "head": "1ed87183778a19a77a732754eeb5c8c28e3c79af",
    "branch": "main",
    "dirty": false,
    "dirty_paths": []
  },
  "time": { "start_utc": "2026-07-08T14:30:00Z", "end_utc": "2026-07-08T14:41:12Z" },
  "tool_versions": { "opa": "1.4.2", "docker": "27.1.1", "python": "3.12.10" },
  "operator": "codex",
  "result": "PASS",
  "notes": ""
}
```

- `git.dirty`/`dirty_paths` 如实记录采集时工作树是否干净，用于证明证据对应的代码状态。
- `result` ∈ `PASS` / `LIMIT` / `BLOCKED` / `INFRA_ERROR`，与 `RESULTS.md` 首行一致。

### 2.4 捕获纪律

- run 全程用 `script -q -c '<cmd>' console.log` 或 `<cmd> 2>&1 | tee -a console.log` 捕获逐字输出，不允许事后重写。
- `commands.txt` 记录真实命令原文（含参数、环境变量前缀），与 `console.log` 对应。
- `artifact-hashes.json` 在**封存前**对最终 run 目录重算一次，保证与实际文件一致。

---

## 3. 封存步骤：`seal-run <run-id>`

对一个已完成的 `runs/<run-id>/`：

1. 重算 `artifact-hashes.json`，覆盖 run 内所有文件（除自身）。
2. 打包 `sealed/<run-id>.tar.gz`，**确定性排序**（`tar --sort=name`，固定 `--owner=0 --group=0 --numeric-owner`，`--mtime` 取 `end_utc`），使同一 run 打包可复现。
3. 计算 `sealed/<run-id>.tar.gz.sha256` —— 即该 run 的**顶层哈希**。
4. 追加一行到本机 `HOST-INDEX.jsonl`，**并打印一条 provenance manifest 记录**（§4 格式），供提交进 git。

封存后 `sealed/<run-id>.tar.gz` 视为不可变；如需修正必须新开 run-id 重跑，不得原地改包。

---

## 4. 信任锚：git 中提交的 provenance manifest

**信任链闭合在 git 仓库里，而不是在 tarball 旁边。** tarball 旁的 `.sha256` 只是便捷校验值，**不是**真相来源——因为攻击者可以同时替换包与其旁边的哈希。真相来源是提交进本仓、推到远端的 manifest：

- 人读：`docs/acceptance/remote-evidence/PROVENANCE.md`
- 机器读：`docs/acceptance/remote-evidence/provenance-manifest.jsonl`

每个已封存 run 追加一条记录并提交：

```json
{"run_id":"l3-r7-opa-20260708T143000Z-lin01","host":"lin01","target":"R7-OPA","end_utc":"2026-07-08T14:41:12Z","tarball_sha256":"<sha256>","file_count":37,"total_bytes":842113,"result":"PASS"}
```

一旦该记录被 commit 并 push，**git 历史 + 远端就是信任锚**：

> 一个被采集回来的 `<run-id>.tar.gz` 是真实的，当且仅当它的 sha256 等于**已提交 manifest** 中记录的 `tarball_sha256`。

验证时以已提交 manifest 为准，**不以** tarball 旁的 `.sha256` 为准。这正是 `status.md` BLOCKED #7 要求的“证明本地 `D:/evidence` 与远端主机执行证据属于同一次真实验收”的绑定关系。

---

## 5. 采集与收束

- **迭代期（live）**：增量拉取整个 `runs/`：
  ```bash
  rsync -avz --partial <host>:~/xa-evidence/runs/ D:/xa-evidence/remote/<host>/runs/
  ```
- **记录期（sealed）**：拉 `sealed/`，逐包对**已提交 manifest** 校验：
  ```bash
  rsync -avz <host>:~/xa-evidence/sealed/ D:/xa-evidence/remote/<host>/sealed/
  # 对每个包：sha256sum 得到值，与 provenance-manifest.jsonl 中该 run_id 的 tarball_sha256 比对
  ```
- **收束**：提交进 git 的 `provenance-manifest.jsonl` 是绑定**本地 ⇄ 远端、跨所有主机**的唯一索引；本地采集镜像固定落在 `D:/xa-evidence/remote/<host>/`，与 manifest 中 `host` 对应。

---

## 6. 辅助脚本（占位，随实现计划落地）

`tools/evidence/` 下的 POSIX 脚本（本规范只定义契约，实现见后续计划）：

| 脚本 | 职责 |
|---|---|
| `new-run.sh <target>` | 生成 `runs/<run-id>/` 骨架，写 `meta.json` 初值，开启 `script` transcript |
| `seal-run.sh <run-id>` | 执行 §3 封存并打印 manifest 记录 |
| `verify-run.sh <run-id>` | 重算并核对 `artifact-hashes.json`，可选核对 tarball 顶层哈希 |
| `collect.sh <host>` | 按 §5 从远端拉取并对已提交 manifest 校验 |

该模块保留 `.log/` 工作日志（每次 ≤300 字）。

---

## 7. 旧证据（legacy locations）

以下旧目录 grandfathered，**不迁移、不重打包**，仅作历史引用：

- `docs/evidence/`（如 `l3-r4-20260705-current/`、`gate1-*`）
- `D:/evidence/`（如 `l3-20260620T090452Z/`、`l3-r8-aibom-20260707T105519Z/`）
- `/mnt/d/evidence/`（如 `l3-r7-20260706T055152Z/`）
- `docs/acceptance/*/evidence/`（如 R8 外部生成器证据）

**所有新 run**（本地与远端）一律走本规范。
