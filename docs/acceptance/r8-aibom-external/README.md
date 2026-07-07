# R8 外部 AIBOM/CycloneDX 生成器交接

状态：`DONE`（2026-07-07 实跑通过）。已用 `@cyclonedx/cdxgen@12.7.0` 真实生成 CycloneDX 1.6 产物并经 XA-Guard 导入 + schema 校验通过；`xa-aibom validate/admit` 正向、篡改、hash mismatch、缺字段和高风险 deny 负测已实跑。结果、证据目录与实测命令见 [`RESULTS.md`](./RESULTS.md)。

> 实测提示：候选命令中的 `--bom-audit` / `--bom-audit-categories ai-bom` 在 cdxgen 12.7.0 中不存在，已在 `RESULTS.md` 用 `--profile research` 替代并记录；`--include-formulation` 会触发 whole-repo 扫描，已刻意不用。下文候选调研内容保留作历史参考。

## 目标

R8 需要证明 XA-Guard 能接收一个合法外部工具生成的真实 CycloneDX 1.6 AIBOM/SBOM，并通过 `xa_guard.aibom.external_generator` 与 `xa-aibom validate/admit` 做哈希、来源、schema 和 artifact 准入校验。

本目录只解决后续 agent 接手前的准备问题：

- 明确一个优先候选外部生成器；
- 提供可扫描的最小样本项目；
- 给出生成、固定哈希、导入校验和证据归档命令；
- 明确哪些内容仍不能作为验收通过声明。

## 目录

| 路径 | 用途 |
|---|---|
| [`candidate-cdxgen.md`](./candidate-cdxgen.md) | `@cyclonedx/cdxgen` 候选来源、许可、优先级和风险 |
| [`samples/python-ai-plugin/`](./samples/python-ai-plugin/) | 最小 AI 插件样本项目，供外部工具扫描 |

## 推荐候选

优先候选：`@cyclonedx/cdxgen` / `cdxgen` / `aibom`。

选择理由：公开开源、Apache-2.0、属于 CycloneDX 生态，官方 README 描述支持 CycloneDX JSON、CycloneDX 1.5-1.7、AI/ML AI-BOM、prompt 文件、AI service、MCP config 和 model metadata。详见 [`candidate-cdxgen.md`](./candidate-cdxgen.md)。

## 样本目录

样本根目录：

```text
docs/acceptance/r8-aibom-external/samples/python-ai-plugin/
├── README.md
├── mcp-server.json
├── prompts/system.prompt.md
├── pyproject.toml
└── src/r8_sample_plugin/__init__.py
```

样本刻意保持最小化：Python 包元数据、一个 MCP server manifest、一个 prompt 文件和一个可导入模块。它不包含真实密钥、网络调用、模型权重或需要执行的业务逻辑。

## 生成命令

以下命令是后续验收候选命令，不表示已在本仓执行成功。执行前需要由接手 agent 固定实际版本，并记录 `cdxgen --version` 或 `aibom --version` 输出。

PowerShell：

```powershell
$Sample = "docs/acceptance/r8-aibom-external/samples/python-ai-plugin"
$Evidence = "D:/evidence/l3-r8-aibom-$(Get-Date -Format yyyyMMddTHHmmssZ)"
New-Item -ItemType Directory -Force -Path $Evidence | Out-Null

# 推荐先固定 npm 包版本，例如 @cyclonedx/cdxgen@12.3.1；版本号必须按实测更新。
npx --yes @cyclonedx/cdxgen@12.3.1 `
  -r `
  --include-formulation `
  --bom-audit `
  --bom-audit-categories ai-bom `
  --spec-version 1.6 `
  -o "$Evidence/aibom.cdxgen.json" `
  $Sample

npx --yes @cyclonedx/cdxgen@12.3.1 --version | Out-File "$Evidence/cdxgen-version.txt" -Encoding utf8
Get-FileHash "$Evidence/aibom.cdxgen.json" -Algorithm SHA256 | ConvertTo-Json | Out-File "$Evidence/aibom.sha256.json" -Encoding utf8
```

Bash：

```bash
sample="docs/acceptance/r8-aibom-external/samples/python-ai-plugin"
evidence="/mnt/d/evidence/l3-r8-aibom-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$evidence"

npx --yes @cyclonedx/cdxgen@12.3.1 \
  -r \
  --include-formulation \
  --bom-audit \
  --bom-audit-categories ai-bom \
  --spec-version 1.6 \
  -o "$evidence/aibom.cdxgen.json" \
  "$sample"

npx --yes @cyclonedx/cdxgen@12.3.1 --version > "$evidence/cdxgen-version.txt"
sha256sum "$evidence/aibom.cdxgen.json" > "$evidence/aibom.sha256"
```

如果 `aibom` CLI 在固定版本中可用，也可以作为第二条候选命令，但必须按真实 `aibom --help` 确认参数后再纳入证据：

```bash
npx --yes --package=@cyclonedx/cdxgen@12.3.1 aibom \
  --spec-version 1.6 \
  -o "$evidence/aibom.aibom-cli.json" \
  "$sample"
```

## XA-Guard 导入校验命令

外部生成后，用 XA-Guard 的只读适配器导入并校验。适配器不会下载或执行外部工具，只读取已有 BOM 文件。

PowerShell：

```powershell
$Bom = "$Evidence/aibom.cdxgen.json"
$Sha = (Get-FileHash $Bom -Algorithm SHA256).Hash.ToLowerInvariant()
$env:PYTHONPATH = "src"
python -c "from pathlib import Path; from xa_guard.aibom.external_generator import ExternalGeneratorSpec, load_external_cyclonedx; bom=Path(r'$Bom'); gen=ExternalGeneratorSpec(name='@cyclonedx/cdxgen', source='https://github.com/cdxgen/cdxgen', version='12.3.1', license_expression='Apache-2.0', commands=(('npx','--yes','@cyclonedx/cdxgen@12.3.1','-r','--include-formulation','--bom-audit','--bom-audit-categories','ai-bom','--spec-version','1.6','-o',str(bom),r'docs/acceptance/r8-aibom-external/samples/python-ai-plugin'),)); ex=load_external_cyclonedx(bom, expected_sha256='$Sha', generator=gen); print({'sha256': ex.sha256, 'specVersion': ex.bom.get('specVersion'), 'components': len(ex.bom.get('components', [])), 'generator': ex.generator.as_dict()})" | Out-File "$Evidence/xa-guard-import-result.txt" -Encoding utf8
```

Bash：

```bash
bom="$evidence/aibom.cdxgen.json"
sha="$(sha256sum "$bom" | awk '{print $1}')"
PYTHONPATH=src python - <<PY | tee "$evidence/xa-guard-import-result.txt"
from pathlib import Path
from xa_guard.aibom.external_generator import ExternalGeneratorSpec, load_external_cyclonedx

bom = Path("$bom")
gen = ExternalGeneratorSpec(
    name="@cyclonedx/cdxgen",
    source="https://github.com/cdxgen/cdxgen",
    version="12.3.1",
    license_expression="Apache-2.0",
    commands=((
        "npx", "--yes", "@cyclonedx/cdxgen@12.3.1", "-r", "--include-formulation",
        "--bom-audit", "--bom-audit-categories", "ai-bom", "--spec-version", "1.6",
        "-o", str(bom), "docs/acceptance/r8-aibom-external/samples/python-ai-plugin",
    ),),
)
exchange = load_external_cyclonedx(bom, expected_sha256="$sha", generator=gen)
print({
    "sha256": exchange.sha256,
    "specVersion": exchange.bom.get("specVersion"),
    "components": len(exchange.bom.get("components", [])),
    "generator": exchange.generator.as_dict(),
})
PY
```

## 最小证据清单

后续真正跑 R8 时，建议归档到 `D:/evidence/l3-r8-aibom-<timestamp>/` 或同等证据目录：

- `cdxgen-version.txt`：外部工具版本输出；
- `aibom.cdxgen.json`：外部生成的 CycloneDX 1.6 JSON；
- `aibom.sha256` 或 `aibom.sha256.json`：产物 SHA-256；
- `xa-guard-import-result.txt`：XA-Guard 导入校验结果；
- `xa-aibom-cli-results.md`：`xa-aibom validate/admit` 正负测矩阵；
- `commands.txt`：实际执行命令，不要只复制本文候选命令；
- `environment.txt`：OS、Node/npm/npx、Python、XA-Guard commit 或工作树摘要；
- `artifact-hashes.json`：证据目录内文件哈希清单。

## 不宣称项

- 不宣称 marketplace/IDE 安装链完成：样本只覆盖本地目录扫描。
- 不宣称 cdxgen 输出完全等同最终 AIBOM 标准：需按实测 BOM 字段检查 prompt/MCP/model/formulation 覆盖。
- 不把 `npx --yes` 当作生产供应链策略：正式证据应固定版本、保留 lock/下载来源、必要时用离线包或 release binary + hash。

## 接手顺序

1. 确认外部工具许可证、版本和安装方式是否被当前团队允许。
2. 在干净环境执行 `cdxgen --help`、`cdxgen --version`，必要时改本文命令。
3. 扫描 `samples/python-ai-plugin/`，确认 `specVersion` 为 `1.6`。
4. 用 `load_external_cyclonedx` 导入并保存结果。
5. 把证据哈希、命令和失败/成功边界写回 `status.md` 与根 `log.md`；只有证据齐全时再考虑更新验收状态。
