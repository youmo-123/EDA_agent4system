"""Master Agent 上下文（跨 Facade 调用共享的只读视图）。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dooragent.orchestration.runtime import OrchestrationRuntime
from dooragent.tooling import ToolRegistry


@dataclass(slots=True)
class MasterContext:
    product_run_root: Path
    orchestration: OrchestrationRuntime
    tool_registry: ToolRegistry
