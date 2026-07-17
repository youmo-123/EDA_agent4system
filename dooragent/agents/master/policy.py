"""Master Policy：Master 决策规则的可测试封装。

- Master 只做监督/决策/发布，不生成 EDA 业务证据
- 具体控制面动作通过 Manifest 中的 master_* Tool 触发
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RoutingDecision:
    """Master 对一个新 Agent Task 的路由结论。"""
    target_role: str            # A1 | A2 | A3
    reason: str
    allowed_tools: list[str]


class MasterPolicy:
    """决定：
      - 一个到达 Master 的请求应路由到哪个 Agent
      - 是否需要打开 Gate 2
      - 一个 Gate 2 应给出哪种 Resolution（默认 CONTINUE_WITH_CONSTRAINTS）
    """

    def route_task(self, task: dict[str, Any]) -> RoutingDecision:
        op = str(task.get("operation", "")).lower()
        if op.startswith("compile") or "simulate" in op or "bottleneck" in op or "hotspot" in op:
            return RoutingDecision(target_role="A1", reason="simulation-analysis",
                                    allowed_tools=[])
        if op.startswith("generate_") or "coverage" in op or "assertion" in op or "test" in op:
            return RoutingDecision(target_role="A2", reason="verification-generation",
                                    allowed_tools=[])
        if op.startswith("synth") or "ppa" in op or "timing" in op or "recommend" in op:
            return RoutingDecision(target_role="A3", reason="ppa-optimization",
                                    allowed_tools=[])
        # 默认交给 A2，方案要求 Master 不写死顺序
        return RoutingDecision(target_role="A2", reason="default", allowed_tools=[])

    def should_open_gate2(self, event: dict[str, Any]) -> tuple[bool, str]:
        kind = str(event.get("kind", ""))
        if "unavailable" in kind or "hash_mismatch" in kind or "timeout" in kind:
            return True, kind
        return False, ""

    def default_resolution(self, thread_reason: str) -> dict[str, Any]:
        # 保守默认：CONTINUE_WITH_CONSTRAINTS，要求补齐证据
        return {
            "resolution": "CONTINUE_WITH_CONSTRAINTS",
            "allowed_actions": ["retry_with_evidence"],
            "forbidden_actions": ["publish_without_evidence"],
            "must_produce": ["evidence_manifest"],
        }
