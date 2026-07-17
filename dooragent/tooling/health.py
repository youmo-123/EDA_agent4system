"""Tool 健康状态机（方案第 4.7 节）。

DECLARED_NOT_BOUND
  → BOUND_UNVERIFIED
    → HEALTHY | DEGRADED | UNAVAILABLE
"""
from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from dooragent.tooling.manifest import ToolManifest


class ToolHealthState(StrEnum):
    DECLARED_NOT_BOUND = "DECLARED_NOT_BOUND"
    BOUND_UNVERIFIED = "BOUND_UNVERIFIED"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


def health_of(manifest: ToolManifest, project_root: Path) -> ToolHealthState:
    """粗粒度启动期健康判定：
      - implementation=mock：HEALTHY（仅用于测试/骨架）
      - implementation=builtin：BOUND_UNVERIFIED（真实探针在运行期）
      - implementation=script：脚本文件存在 → BOUND_UNVERIFIED，否则 DECLARED_NOT_BOUND
      - implementation=external：BOUND_UNVERIFIED；具体外部二进制在运行前 healthcheck
      - implementation=adapter：BOUND_UNVERIFIED
    """
    impl = manifest.implementation
    if impl == "mock":
        return ToolHealthState.HEALTHY
    if impl == "script":
        entry = manifest.entrypoint.split()[0] if manifest.entrypoint else ""
        if not entry:
            return ToolHealthState.DECLARED_NOT_BOUND
        # 支持相对项目根路径
        candidate = project_root / entry
        if candidate.exists():
            return ToolHealthState.BOUND_UNVERIFIED
        return ToolHealthState.DECLARED_NOT_BOUND
    if impl in ("builtin", "external", "adapter"):
        return ToolHealthState.BOUND_UNVERIFIED
    return ToolHealthState.DECLARED_NOT_BOUND


def agent_health(agent_role: str) -> dict:  # pragma: no cover - used by Manifest healthcheck reference
    """Manifest 中默认 `dooragent.tooling.health:agent_health` 的最小实现。"""
    return {"state": ToolHealthState.HEALTHY, "role": agent_role}
