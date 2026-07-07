# R8 外部 AIBOM/CycloneDX 生成器实跑结果

状态：`PASS（外部 CycloneDX 1.6 导入 + MCP AI-BOM 语义覆盖）`。
执行日期：2026-07-07（UTC）。执行环境与哈希见证据目录。

## 结论摘要

- 用合法开源外部工具 `@cyclonedx/cdxgen@12.7.0`（Apache-2.0）扫描最小样本，真实生成了 CycloneDX `specVersion: "1.6"` JSON。
- XA-Guard 只读适配器 `xa_guard.aibom.external_generator.load_external_cyclonedx` 成功导入：SHA-256 绑定校验通过、CycloneDX schema 校验通过（`jsonschema` 路径）。
- 产物包含真实 AI-BOM 语义信号：MCP SDK 被识别为组件并带 `cdx:mcp:*` 属性和 `mcp-sdk`/`official-mcp-sdk` 标签，因此 R8 不止是普通 SBOM 导入，具备 AI-BOM 部分语义覆盖。

## 证据目录

- 归档源：`D:/evidence/l3-r8-aibom-20260707T105519Z/`
- 仓内副本：`docs/acceptance/r8-aibom-external/evidence/l3-r8-aibom-20260707T105519Z/`

| 文件 | 内容 |
|---|---|
| `aibom.cdxgen.json` | cdxgen 生成的 CycloneDX 1.6 产物（32 组件，SHA-256 见下） |
| `aibom.sha256` | 产物 SHA-256 |
| `cdxgen-version.txt` | `cdxgen --version` 输出（12.7.0） |
| `xa-guard-import-result.txt` | XA-Guard 导入 + schema 校验结果（`import: PASS`） |
| `commands.txt` | 实际执行命令与 flag 漂移说明 |
| `environment.txt` | OS/Node/npm/Python/jsonschema/XA-Guard commit |
| `artifact-hashes.json` | 证据目录文件 SHA-256 清单 |

产物 SHA-256：`6a43e3a3b8637f7cc05c328a9261311825e4ba08ec119faf1ec0699dea1db100`

## 与候选命令的差异（重要）

`README.md` 候选命令中的 `--bom-audit` 与 `--bom-audit-categories ai-bom` **在 cdxgen 12.7.0 中不存在**，已按实测 `--help` 移除。AI/ML 语义由 `--profile`（本次用 `research`）驱动，MCP 检测与这两个已废弃 flag 无关。

同时刻意 **未使用** `--include-formulation`：该 flag 会让 cdxgen 遍历整个 git 仓库并把仓库级文件清单写入 formulation（首跑产物因此膨胀到 ~986 KB 并泄露 `docs/references/...` 等无关路径）。去掉后产物为 22.7 KB，作用域限定在样本依赖图，证据更干净可复核。

实际命令：

```bash
export HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897 FETCH_LICENSE=false
npx --yes @cyclonedx/cdxgen@12.7.0 \
  -r -t python --profile research --spec-version 1.6 \
  -o "$evidence/aibom.cdxgen.json" \
  docs/acceptance/r8-aibom-external/samples/python-ai-plugin
```

## 实跑中发现并修复的 XA-Guard 缺陷

首次导入 **失败**：cdxgen 12.7.0 按 CycloneDX 1.5+ 规范把 `metadata.tools` 写成对象形式
`{"components": [...], "services": [...]}`，而 XA-Guard 内置子集 schema
（`src/xa_guard/aibom/schema/cyclonedx-1.6.subset.schema.json`）仅允许旧版数组形式，
导致合法的 CycloneDX 1.6 被拒。

修复：将 `metadata.tools` 放宽为 `anyOf: [array, object{components,services}]`，
兼容旧生产者的数组形式与新生产者的对象形式。已补两条回归测试
（`tests/unit/test_aibom_schema_validator.py::TestMetadataToolsForms`）。修复后导入通过。

## 不宣称项（延续原边界）

- 不宣称 marketplace/IDE 安装链完成：样本只覆盖本地目录扫描。
- 不宣称完整 AI-BOM 标准全覆盖：本次覆盖到 MCP SDK 组件语义；prompt 文件 / model 权重等仅在 `--include-formulation`（whole-repo 扫描）下以文件形式出现，未纳入干净产物。
- 不把 `npx --yes` + 代理当作生产供应链策略：正式证据应固定版本、保留 lock/离线包与下载来源哈希。
