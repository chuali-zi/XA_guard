# AIBOM 外部生成器静态交换适配

## 范围

`xa_guard.aibom.external_generator` 接收已经生成的 CycloneDX JSON，不发现、下载或执行任何外部生成器。该边界用于离线 fixture、受控流水线产物和人工提供的产物交换；它不是外部工具运行器。

R8 入口见 [`r8-aibom-external/README.md`](./r8-aibom-external/README.md)，实跑结果见 [`r8-aibom-external/RESULTS.md`](./r8-aibom-external/RESULTS.md)。2026-07-07 已用 `@cyclonedx/cdxgen@12.7.0`（Apache-2.0）真实生成 CycloneDX 1.6 产物，经 `load_external_cyclonedx` 完成 SHA-256 绑定与 schema 校验（`import: PASS`），并覆盖到 MCP SDK 的 AI-BOM 语义信号。

本仓库不内置任何第三方命令，也不由 XA-Guard 自动执行外部生成器。调用方必须记录自己实际使用并已核验的命令参数、版本、许可证和产物哈希。

## 必填来源记录

每次导入必须构造 `ExternalGeneratorSpec`，显式填写生成器名称、来源、固定版本、许可证表达式和实际命令清单。每条命令按参数数组保存，不使用 shell 字符串。

适配器保存这些声明，但不替调用方验证来源真实性、许可证合规性或命令语义。依赖和工具的采用仍需项目合规审核。

## 校验顺序

1. 读取 `bytes` 或本地 `pathlib.Path`，默认拒绝超过 16 MiB 的产物；
2. 对原始字节计算 SHA-256，与调用方提供的 64 位十六进制摘要进行恒定时间比较；
3. 严格按 UTF-8 JSON 解析，并拒绝重复对象键；
4. 要求 `specVersion` 精确为 `1.6`；
5. 调用现有 `validate_cyclonedx`，复用仓库 schema 与引用完整性检查。

任何一步失败都会抛出 `ExternalGeneratorError`，不返回部分可信结果。

## 静态 fixture

测试中的 `fixture-generator`、`example.invalid` 来源及其参数仅为不可访问的 fixture 数据，不代表真实产品或官方 CLI。单元测试只构造本地字节和临时文件，不访问网络，也不启动外部进程。

## R8 候选准备状态

- 候选工具：`@cyclonedx/cdxgen` / `cdxgen` / `aibom`。
- 样本目录：`docs/acceptance/r8-aibom-external/samples/python-ai-plugin/`。
- 命令与证据清单：[`r8-aibom-external/README.md`](./r8-aibom-external/README.md)。
- 已完成（2026-07-07）：固定版本 `12.7.0` 实跑、真实 CycloneDX 1.6 产物、XA-Guard 导入校验输出（`import: PASS`）、artifact hash manifest；证据见 [`RESULTS.md`](./r8-aibom-external/RESULTS.md)。
- 仍缺：真实 marketplace/IDE 安装链证据；完整 AI-BOM 标准全字段覆盖（当前覆盖 MCP SDK 语义）。
