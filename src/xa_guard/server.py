"""XA-Guard MCP Server 主入口。

run_server(config_path) 流程：
1. 加载 XAGuardConfig
2. 实例化 6 关卡（按 cfg.gates.* 选项）
3. 启动 DownstreamRouter（连接所有下游 MCP server）
4. 构造 Pipeline
5. 启动 upstream（stdio 或 Streamable HTTP）

CLI 用法：
    python -m xa_guard.server --config configs/xa-guard.yaml
    或
    xa-guard --config configs/xa-guard.yaml
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from xa_guard.config import XAGuardConfig
from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.gates.gate2_plan import Gate2Plan
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.gates.gate5_sandbox import Gate5Sandbox
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.pipeline import Pipeline
from xa_guard.policy.hot_reload import OverlayWatcher
from xa_guard.policy.layered import LayeredPolicySource, set_global_source
from xa_guard.proxy.downstream import DownstreamRouter
from xa_guard.proxy.upstream import run_stdio, run_streamable_http

log = logging.getLogger("xa_guard.server")


def _init_layered_policy(cfg: XAGuardConfig) -> tuple[LayeredPolicySource | None, OverlayWatcher | None]:
    """读 cfg.gates['policy_layered'] 决定是否启用双层策略 + 热加载。"""
    layered_cfg = cfg.gates.get("policy_layered")
    if layered_cfg is None or not layered_cfg.enabled:
        return None, None
    opts = layered_cfg.options
    src = LayeredPolicySource(
        manifest_path=opts.get("baseline_manifest", "policies/baseline_manifest.yaml"),
        overlay_root=opts.get("overlay_root", "policies/overlay"),
    )
    set_global_source(src)
    log.info(
        "LayeredPolicySource ready: bundle_sha=%s stats=%s",
        src.bundle_sha[:12], src.stats(),
    )
    watcher: OverlayWatcher | None = None
    if opts.get("hot_reload", True):
        watcher = OverlayWatcher(
            src,
            opts.get("overlay_root", "policies/overlay"),
        )
        if watcher.start():
            log.info("OverlayWatcher started")
    return src, watcher


def build_pipeline(cfg: XAGuardConfig) -> Pipeline:
    _init_layered_policy(cfg)
    return Pipeline(
        gate1=Gate1Input(cfg.gate("gate1")),
        gate2=Gate2Plan(cfg.gate("gate2")),
        gate3=Gate3Policy(cfg.gate("gate3")),
        gate4=Gate4Taint(cfg.gate("gate4")),
        gate5=Gate5Sandbox(cfg.gate("gate5")),
        gate6=Gate6Audit(cfg.gate("gate6")),
        cfg=cfg,
    )


async def run_server(cfg: XAGuardConfig) -> None:
    pipeline = build_pipeline(cfg)
    router = DownstreamRouter(cfg.downstream)
    await router.start()
    try:
        if cfg.upstream.transport == "stdio":
            await run_stdio(pipeline, router)
        else:
            await run_streamable_http(pipeline, router, cfg.upstream.host, cfg.upstream.port)
    finally:
        await router.stop()


def main() -> None:
    parser = argparse.ArgumentParser(prog="xa-guard")
    parser.add_argument(
        "--config",
        default="configs/xa-guard.yaml",
        help="YAML 配置路径（默认 configs/xa-guard.yaml）",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        raise SystemExit(f"config not found: {cfg_path}")
    cfg = XAGuardConfig.from_yaml(cfg_path)
    asyncio.run(run_server(cfg))


if __name__ == "__main__":
    main()
