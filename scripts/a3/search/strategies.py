#!/usr/bin/env python3
"""a3 search/strategies：按 Strategy Catalog 选择尚未评价的合法策略。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.artifact_io import now_iso
from scripts.common.atomic_io import write_json_atomic
from scripts.common.script_cli import ScriptResult, run_script


def _load_catalog(project_root: Path) -> list[dict]:
    cfg = project_root / "configs" / "algorithms" / "a3-strategies.toml"
    if not cfg.exists():
        return []
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib
    return tomllib.loads(cfg.read_text(encoding="utf-8")).get("strategies", [])


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    history = params.get("history") or []
    max_plan = int(params.get("max_plan", 5))
    catalog = _load_catalog(REPO_ROOT)
    if not catalog:
        return ScriptResult(status="unavailable", error_code="CAPABILITY_UNAVAILABLE",
                            error={"message": "strategy catalog empty"})
    seen = {h.get("strategy_id") for h in history}
    planned = [s["strategy_id"] for s in catalog if s["strategy_id"] not in seen][:max_plan]
    plan = {
        "experiment_id": f"exp-{len(history)}",
        "planned_strategies": planned,
        "reason": f"catalog picks; skipping seen {sorted(seen)}",
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "strategy-plan.json", plan)
    return ScriptResult(
        status="completed" if planned else "partial",
        output_artifact_refs=["strategy-plan.json"],
        raw_metrics={"planned": len(planned), "catalog": len(catalog),
                     "seen": len(seen)},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a3_search_strategies",
        description="Pick next strategies from catalog",
        handler=handle,
    ))
