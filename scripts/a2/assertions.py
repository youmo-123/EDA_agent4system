#!/usr/bin/env python3
"""a2 assertions：生成组合/时序/协议断言候选。"""
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


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    design_ref = params.get("design_ref", "")
    if not design_ref or not Path(design_ref).exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "design_ref missing"})
    design = json.loads(Path(design_ref).read_text(encoding="utf-8"))
    ports = design.get("ports", [])
    candidates = []
    if any(p["name"].lower().startswith("valid") for p in ports):
        candidates.append({
            "kind": "handshake",
            "expression": "!(valid && !ready) |=> valid",
            "confidence": 0.6,
            "note": "auto-generated valid/ready handshake candidate",
        })
    if design.get("resets"):
        rst = design["resets"][0]
        candidates.append({
            "kind": "reset_stability",
            "expression": f"!{rst} |-> $stable(state)",
            "confidence": 0.5,
        })
    payload = {"items": candidates, "created_at": now_iso()}
    write_json_atomic(work_dir / "assertion-candidates.json", payload)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["assertion-candidates.json"],
        raw_metrics={"count": len(candidates)},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a2_assertion_inferencer",
        description="Infer combinational/temporal/protocol assertion candidates",
        handler=handle,
    ))
