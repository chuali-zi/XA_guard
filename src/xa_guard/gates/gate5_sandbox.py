"""关卡 5 · 隔离办公间（沙箱路由） — 赛题方向 2 工程兜底。

子 agent 实施职责：
- 根据 ctx.risk_level 路由：
    GREEN → 直通（native）
    YELLOW → Docker（默认 image, 只读 FS, no network）
    RED → Docker + gVisor runtime（若可用，否则降级为普通 Docker）
- 沙箱实际执行由 proxy.downstream 触发（关卡 5 主要负责"标记和路由决定"）
- demo 阶段默认禁用 Docker（cfg.gate5.enabled=false），只输出"路由决策"

接口契约：
- 输入：GateContext.risk_level（或前一关卡 gate2 写入的 metadata["risk_level"]）
- 输出：GateResult.decision = ALLOW + metadata.sandbox_mode ∈ {native, docker, docker_gvisor}
- 不做真实拦截（路由决策性质）
"""
from __future__ import annotations

import time

from xa_guard.gates.base import Gate, GateStage
from xa_guard.types import Decision, GateContext, GateResult, RiskLevel


_RISK_TO_MODE: dict[RiskLevel, str] = {
    RiskLevel.GREEN: "native",
    RiskLevel.YELLOW: "docker",
    RiskLevel.RED: "docker_gvisor",
}


class Gate5Sandbox(Gate):
    name = "gate5_sandbox"
    supported_stages = (GateStage.INBOUND,)

    def __call__(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        """覆盖 base.__call__：enabled=false 不走 disabled 短路，而是返回 native 路由。"""
        if stage not in self.supported_stages:
            return GateResult(gate_name=self.name, decision=Decision.ALLOW, note=f"stage {stage} skipped")
        t0 = time.perf_counter()
        try:
            result = self.evaluate(ctx, stage)
        except Exception as exc:
            return GateResult(
                gate_name=self.name,
                decision=Decision.WARN,
                risks=[f"gate_error: {type(exc).__name__}: {exc}"],
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        result.latency_ms = (time.perf_counter() - t0) * 1000
        if not result.gate_name:
            result.gate_name = self.name
        return result

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        # demo：cfg.enabled=false 时统一走 native，避免依赖 Docker
        if not self.cfg.enabled:
            return GateResult(
                gate_name=self.name,
                decision=Decision.ALLOW,
                metadata={"sandbox_mode": "native"},
                note="docker disabled in demo",
            )

        risk = self._resolve_risk(ctx)
        mode = _RISK_TO_MODE.get(risk, "native")

        # 若配置中要求 gVisor 但仅在 RED 时启用；非 RED 即使 runtime=runsc 也不强制
        runtime = self.opt("runtime", "runc")
        if mode == "docker_gvisor" and runtime != "runsc":
            # 配置未提供 gVisor runtime → 降级 docker
            mode = "docker"
            note = "gVisor runtime unavailable, degrade to docker"
        else:
            note = f"route by risk={risk.value}"

        return GateResult(
            gate_name=self.name,
            decision=Decision.ALLOW,
            metadata={
                "sandbox_mode": mode,
                "docker_image": self.opt("docker_image", "xa-guard/sandbox:latest"),
                "runtime": runtime,
                "risk_level": risk.value,
            },
            note=note,
        )

    @staticmethod
    def _resolve_risk(ctx: GateContext) -> RiskLevel:
        # 优先取前一关卡 gate2 写入 metadata 的 risk_level（可能为 str 或 enum）
        for r in ctx.gate_results:
            if r.gate_name in ("gate2_plan", "gate2"):
                rl = r.metadata.get("risk_level")
                if isinstance(rl, RiskLevel):
                    return rl
                if isinstance(rl, str):
                    try:
                        return RiskLevel(rl)
                    except ValueError:
                        pass
        return ctx.risk_level or RiskLevel.GREEN
