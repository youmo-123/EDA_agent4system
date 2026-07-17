"""Tool Result 封装（与 interfaces/tools/common-result.schema.json 对齐）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ToolStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


# 退出码 → ToolStatus（方案 14.5.1 节）
EXIT_CODE_MAP: dict[int, ToolStatus] = {
    0: ToolStatus.COMPLETED,
    2: ToolStatus.FAILED,          # invalid request
    3: ToolStatus.UNAVAILABLE,     # tool unavailable
    4: ToolStatus.FAILED,          # tool failed
    5: ToolStatus.FAILED,          # output invalid
    124: ToolStatus.TIMEOUT,
    130: ToolStatus.CANCELLED,
}


@dataclass(slots=True)
class ToolResult:
    tool_id: str
    tool_interface_version: str
    request_id: str
    status: ToolStatus
    output_artifact_refs: list[str] = field(default_factory=list)
    raw_metrics: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[Any] = field(default_factory=list)
    wall_time_s: float = 0.0
    error: dict[str, Any] | None = None
    error_code: str | None = None
    tool_versions: dict[str, Any] = field(default_factory=dict)
    command_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "tool_interface_version": self.tool_interface_version,
            "request_id": self.request_id,
            "status": self.status.value,
            "output_artifact_refs": self.output_artifact_refs,
            "raw_metrics": self.raw_metrics,
            "diagnostics": self.diagnostics,
            "wall_time_s": self.wall_time_s,
            "error": self.error,
            "error_code": self.error_code,
            "tool_versions": self.tool_versions,
            "command_refs": self.command_refs,
        }

    @classmethod
    def unsupported(cls, tool_id: str, request_id: str, reason: str) -> "ToolResult":
        return cls(
            tool_id=tool_id,
            tool_interface_version="1.0",
            request_id=request_id,
            status=ToolStatus.UNSUPPORTED,
            error={"message": reason},
            error_code="TOOL_NOT_IMPLEMENTED",
        )

    @classmethod
    def unavailable(cls, tool_id: str, request_id: str, reason: str) -> "ToolResult":
        return cls(
            tool_id=tool_id,
            tool_interface_version="1.0",
            request_id=request_id,
            status=ToolStatus.UNAVAILABLE,
            error={"message": reason},
            error_code="CAPABILITY_UNAVAILABLE",
        )
