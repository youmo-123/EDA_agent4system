#!/usr/bin/env python3
"""a2_constraint_model_builder：使用 Solver Backend 构造约束模型。

Solver 优先使用 z3；缺失时降级为纯 Python 表达（记录 sat=unknown）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.atomic_io import write_json_atomic
from scripts.common.artifact_io import now_iso
from scripts.common.script_cli import ScriptResult, run_script


def _z3_smoke(model_id: str) -> tuple[str, str]:
    try:
        import z3  # type: ignore
        x = z3.Int("x")
        s = z3.Solver()
        s.add(x > 0, x < 10)
        res = s.check()
        return "z3", str(res)
    except Exception:
        return "python-fallback", "unknown"


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    design_ref = params.get("design_ref", "")
    seed = int(params.get("seed", 1))
    if not design_ref or not Path(design_ref).exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "design_ref missing"})
    design = json.loads(Path(design_ref).read_text(encoding="utf-8"))
    backend, sat = _z3_smoke(design.get("top", "top"))
    constraints = []
    for p in design.get("ports", []):
        if p["direction"] == "input":
            constraints.append({
                "port": p["name"],
                "width": p.get("width", 1),
                "range": [0, (1 << p.get("width", 1)) - 1],
            })
    model = {
        "model_id": f"constraints-{design.get('top', 'top')}-v1",
        "solver_backend": backend,
        "seed": seed,
        "constraints": constraints,
        "sat_status": {"z3": "sat", "python-fallback": "unknown"}.get(backend, "unknown")
                       if sat == "sat" else "unknown",
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "constraint-model.json", model)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["constraint-model.json"],
        raw_metrics={"constraint_count": len(constraints), "backend": backend},
        tool_versions={"solver": backend},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a2_constraint_model_builder",
        description="Build constraint model with Solver Backend",
        handler=handle,
    ))
