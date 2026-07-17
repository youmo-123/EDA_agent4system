"""可选 Tool Adapter 基类；只在存在特殊外部协议时使用。

绝大多数 Tool 通过 ScriptRunner + Manifest 即可，无须每个 Tool 都写 Adapter。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dooragent.tooling.result import ToolResult, ToolStatus


class BaseAdapter:
    """Adapter 接口：接收 Tool Request dict，返回 ToolResult。"""

    tool_id: str = ""
    tool_interface_version: str = "1.0"

    def health(self) -> dict[str, Any]:  # pragma: no cover - override
        return {"state": "BOUND_UNVERIFIED"}

    def invoke(self, request: dict[str, Any]) -> ToolResult:  # pragma: no cover
        raise NotImplementedError


@dataclass
class MockAdapter(BaseAdapter):
    """确定性 Mock Adapter；用于测试与骨架冒烟。

    - 永远返回 completed，raw_metrics 中包含 request 摘要
    - 不产生任何真实副作用
    - 不允许在生产 Manifest 中使用（Manifest 层由 registry.strict 检查）
    """

    tool_id: str = "mock_tool"

    def health(self) -> dict[str, Any]:
        return {"state": "HEALTHY", "implementation": "mock"}

    def invoke(self, request: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_id=request.get("tool_id", self.tool_id),
            tool_interface_version=request.get("tool_interface_version", "1.0"),
            request_id=request.get("request_id", "mock-req"),
            status=ToolStatus.COMPLETED,
            raw_metrics={"mock": True, "parameters_keys": sorted((request.get("parameters") or {}).keys())},
            wall_time_s=0.0,
        )
