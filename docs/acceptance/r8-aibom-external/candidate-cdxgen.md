# 候选：CycloneDX cdxgen / aibom

状态：候选已调研，待本机或受控环境实跑。

## 基本信息

| 项 | 内容 |
|---|---|
| 项目 | `cdxgen/cdxgen`，npm 包 `@cyclonedx/cdxgen` |
| 来源 | <https://github.com/CycloneDX/cdxgen> |
| 文档 | <https://cdxgen.github.io/cdxgen> |
| 许可证 | Apache-2.0 |
| 主要输出 | CycloneDX JSON；README 说明支持 CycloneDX 1.5-1.7，并支持 SPDX 3.0.1 JSON-LD 导出 |
| AI 相关 | README 说明支持 AI/ML AI-BOM、prompt files、AI services、MCP configs、model metadata、AI-governance/security/performance/agentic findings |
| 推荐命令族 | `cdxgen`；如固定版本中可用，也可补测 `aibom` alias |

## 为什么作为 R8 优先候选

- 与当前 XA-Guard 外部交换边界匹配：外部工具负责生成 CycloneDX 1.6 JSON，XA-Guard 只做离线读取、哈希绑定和 schema 校验。
- 与 `docs/references/literature/03_supply_chain/CycloneDX-1.6.md` 的标准选择一致。
- 许可证为 Apache-2.0，适合先作为合法开源候选进入验收准备。
- 支持 `--spec-version 1.6`，可以满足 `xa_guard.aibom.external_generator` 当前只接受 CycloneDX `specVersion == "1.6"` 的约束。

## 待核验点

- 实际固定版本号：本文示例使用 `12.3.1`，接手 agent 必须以实测 `--version` 和下载来源为准。
- CLI 参数漂移：`--include-formulation`、`--bom-audit-categories ai-bom`、`aibom` alias 需要按固定版本 `--help` 复核。
- 网络与脚本策略：`npx --yes` 会访问 npm registry；正式环境如禁止联网，应改用预下载包、release binary 或容器镜像，并保留 hash。
- 输出覆盖度：需要检查 BOM 中是否实际包含 prompt/MCP/config/model 相关字段；若 cdxgen 对该最小样本只产生普通 SBOM，则 R8 只能宣称“外部 CycloneDX 产物导入”，不能宣称完整 AI-BOM 语义覆盖。
- 真实安装链：本候选只覆盖本地样本扫描，不覆盖 Trae/Cursor marketplace 或 IDE 插件安装链。

## 采用门槛

后续 agent 至少需要拿到以下证据，才可把 R8 从 `BLOCKED` 改成更具体的实测状态：

- 固定版本工具的来源、许可证和版本输出；
- 外部工具生成的 `specVersion: "1.6"` CycloneDX JSON；
- BOM 文件 SHA-256 与 XA-Guard `load_external_cyclonedx` 导入结果；
- 实际执行命令和环境信息；
- 对输出字段的人工复核记录，说明它是 SBOM、AI-BOM，还是 AI-BOM 部分覆盖。
