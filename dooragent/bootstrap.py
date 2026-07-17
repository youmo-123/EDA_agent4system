"""Bootstrap：装配 orchestration + tooling + agents + workspace，提供 build_master_facade。

用途：
- CLI `run` 时构造一个 MasterFacade 承接产品请求
- 单元/集成测试可复用同一 bootstrap
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from dooragent.agents.master import MasterAgent, MasterContext, MasterFacade
from dooragent.orchestration.runtime import OrchestrationRuntime
from dooragent.tooling import ToolRegistry


@dataclass(slots=True)
class BootstrapResult:
    product_run_root: Path
    tool_registry: ToolRegistry
    orchestration: OrchestrationRuntime
    master_facade: MasterFacade
    config: dict[str, Any]


def load_default_config(project_root: Path) -> dict[str, Any]:
    cfg_path = project_root / "configs" / "default.toml"
    if not cfg_path.exists():
        return {}
    with cfg_path.open("rb") as fh:
        return tomllib.load(fh)


def find_project_root(start: Path | None = None) -> Path:
    """向上寻找含 configs/default.toml 的目录作为项目根。"""
    p = (start or Path.cwd()).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / "configs" / "default.toml").exists() and (candidate / "dooragent").exists():
            return candidate
    return p


def bootstrap(project_root: Path | None = None) -> BootstrapResult:
    root = find_project_root(project_root)
    cfg = load_default_config(root)
    manifest_dirs = [
        root / "configs" / "tool-manifests" / r
        for r in ("master", "a1", "a2", "a3")
    ]
    registry = ToolRegistry(project_root=root, manifest_dirs=manifest_dirs)
    orchestration = OrchestrationRuntime(root)
    master = MasterFacade(MasterContext(
        product_run_root=root,
        orchestration=orchestration,
        tool_registry=registry,
    ))
    return BootstrapResult(
        product_run_root=root,
        tool_registry=registry,
        orchestration=orchestration,
        master_facade=master,
        config=cfg,
    )
