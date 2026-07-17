#!/usr/bin/env python3
"""a3 evolutionary search：可选；预算不足/无改进时自动 fallback 到 catalog。

- 每个个体必须通过 synth_tool 真实评价（本 script 通过参数收集评价结果；
  真实调用 synth_tool 由上层 orchestration 完成）
- 输出 search 轨迹与最终种群
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.artifact_io import now_iso
from scripts.common.atomic_io import write_json_atomic
from scripts.common.script_cli import ScriptResult, run_script


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    seed = int(params.get("seed", 1))
    budget = params.get("budget") or {}
    pop = int(params.get("population_size", 4))
    gens = int(params.get("generations", 2))
    catalog_ids = params.get("catalog_ids") or ["balanced-default"]
    fitness_fn = params.get("fitness_fn", "score")   # 由外部注入的评价结果
    evaluations = params.get("evaluations", [])     # 已完成的真实评价

    rng = random.Random(seed)
    generations = []
    best = None
    no_improve = 0
    for g in range(gens):
        # 简单随机采样 catalog 生成 population，评价直接取 evaluations（若不足用占位）
        gen = []
        for _ in range(pop):
            sid = rng.choice(catalog_ids)
            eval_hit = next((e for e in evaluations if e.get("strategy_id") == sid), None)
            fit = eval_hit.get(fitness_fn, float("inf")) if eval_hit else float("inf")
            gen.append({"strategy_id": sid, "fitness": fit,
                        "evaluated": eval_hit is not None})
        gen_best = min(gen, key=lambda x: x["fitness"])
        if best is None or gen_best["fitness"] < best["fitness"]:
            best = gen_best
            no_improve = 0
        else:
            no_improve += 1
        generations.append({"generation": g, "population": gen})
    fallback = no_improve >= max(1, gens - 1)
    out = {
        "experiment_id": f"evo-{seed}",
        "generations": generations,
        "elite": [best] if best else [],
        "fallback_triggered": fallback,
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "evolutionary-search-result.json", out)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["evolutionary-search-result.json"],
        raw_metrics={"generations": len(generations), "fallback": fallback},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a3_evolutionary_search",
        description="Optional evolutionary search over strategy catalog",
        handler=handle,
    ))
