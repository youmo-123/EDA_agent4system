from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from dooragent.tooling import ToolRegistry


@dataclass(slots=True)
class A3Context:
    product_run_root: Path
    tool_registry: ToolRegistry
