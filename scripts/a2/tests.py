#!/usr/bin/env python3
"""a2_test_generator：使用固定 PRNG 或 solver enumeration 生成测试序列。"""
from __future__ import annotations

import json
import random
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
    constraints_ref = params.get("constraints_ref", "")
    seed = int(params.get("seed", 1))
    count = int(params.get("count", 100))
    if not constraints_ref or not Path(constraints_ref).exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "constraints_ref missing"})
    con = json.loads(Path(constraints_ref).read_text(encoding="utf-8"))
    rng = random.Random(seed)
    tests_dir = work_dir / "generated_tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries = []
    for i in range(count):
        stim = {}
        for c in con.get("constraints", []):
            lo, hi = c["range"]
            stim[c["port"]] = rng.randint(lo, hi)
        test = {"test_id": f"t-{i:05d}", "seed": seed, "stimulus": stim}
        p = tests_dir / f"t-{i:05d}.json"
        p.write_text(json.dumps(test), encoding="utf-8")
        manifest_entries.append({"test_id": test["test_id"], "path": f"generated_tests/{p.name}"})
    manifest = {
        "manifest_id": f"tests-seed{seed}-n{count}",
        "seed": seed,
        "count": count,
        "constraints_ref": constraints_ref,
        "entries": manifest_entries,
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "test-manifest.json", manifest)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["test-manifest.json", "generated_tests/"],
        raw_metrics={"count": count, "seed": seed},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a2_test_generator",
        description="Emit deterministic test sequences",
        handler=handle,
    ))
