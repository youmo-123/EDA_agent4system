#!/usr/bin/env python3
"""a3_netlist_validator：校验 netlist 非空、TOP 一致、所有 cell 来自 Liberty。"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.artifact_io import now_iso
from scripts.common.atomic_io import write_json_atomic
from scripts.common.script_cli import ScriptResult, run_script


_MODULE_RE = re.compile(r"module\s+([A-Za-z_]\w*)")
_CELL_RE = re.compile(r"^\s*([A-Za-z_][\w$]*)\s+(?:\\\S+|\w+)\s*\(", re.MULTILINE)


def _parse_liberty_cells(lib_path: Path) -> set[str]:
    cells = set()
    if not lib_path.exists():
        return cells
    text = lib_path.read_text(encoding="utf-8", errors="replace")
    # 极简 Liberty 解析：抓 `cell (NAME)`
    for m in re.finditer(r"cell\s*\(\s*([A-Za-z_][\w$]*)\s*\)", text):
        cells.add(m.group(1))
    return cells


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    netlist = Path(params.get("netlist_ref") or "")
    top = params.get("top", "")
    library = Path(params.get("technology_library_ref") or "")
    if not netlist.exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "netlist_ref missing"})
    text = netlist.read_text(encoding="utf-8", errors="replace")
    reasons: list[str] = []
    if netlist.stat().st_size == 0:
        reasons.append("empty netlist")
    modules = set(_MODULE_RE.findall(text))
    if top and top not in modules:
        reasons.append(f"top {top} not present in netlist modules {sorted(modules)}")

    liberty_cells = _parse_liberty_cells(library) if library.exists() else set()
    cell_instances = set(_CELL_RE.findall(text)) - {"module", "endmodule",
                                                     "input", "output", "wire",
                                                     "assign", "reg", "logic", "inout"}
    unresolved = []
    if liberty_cells:
        for c in cell_instances:
            if c not in liberty_cells and c not in modules:
                unresolved.append(c)
        if unresolved:
            reasons.append(f"unresolved cells: {sorted(unresolved)[:10]}")

    validation = {
        "status": "valid" if not reasons else "invalid",
        "reasons": reasons,
        "cell_count": len(cell_instances),
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "netlist-validation.json", validation)
    return ScriptResult(
        status="completed" if not reasons else "failed",
        error_code=None if not reasons else "A3_MAPPING_FAILED",
        output_artifact_refs=["netlist-validation.json"],
        raw_metrics=validation,
        error=None if not reasons else {"reasons": reasons},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a3_netlist_validator",
        description="Validate netlist against TOP and Liberty",
        handler=handle,
    ))
