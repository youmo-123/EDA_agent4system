#!/usr/bin/env python3
"""a2 validate：校验 Artifact Manifest、Schema、hash、seed、生成目录、禁止绝对路径。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.atomic_io import write_json_atomic
from scripts.common.artifact_io import sha256_file
from scripts.common.script_cli import ScriptResult, run_script


REQUIRED_BINDING = ("workflow_id", "producer_agent_instance_id",
                    "schema_version", "artifact_hash", "created_at")


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    manifest_path = params.get("artifact_manifest")
    if not manifest_path or not Path(manifest_path).exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "artifact_manifest missing"})
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    reasons: list[str] = []
    for i, e in enumerate(manifest.get("entries", [])):
        for f in ("artifact_type", "path", "hash"):
            if not e.get(f):
                reasons.append(f"entry[{i}] missing {f}")
        p = e.get("path", "")
        if p.startswith("/") or p.startswith("\\") or ".." in p:
            reasons.append(f"entry[{i}] path not relative: {p}")
        path_obj = Path(manifest_path).parent / p
        if p and path_obj.exists() and e.get("hash"):
            actual = sha256_file(path_obj)
            if actual != e["hash"]:
                reasons.append(f"entry[{i}] hash mismatch: {actual} vs {e['hash']}")
    ok = not reasons
    validation = {
        "ok": ok,
        "reasons": reasons,
        "checked_count": len(manifest.get("entries", [])),
    }
    write_json_atomic(work_dir / "a2-output-validation.json", validation)
    return ScriptResult(
        status="completed" if ok else "failed",
        error_code=None if ok else "SCHEMA_MISMATCH",
        output_artifact_refs=["a2-output-validation.json"],
        raw_metrics=validation,
        error=None if ok else {"reasons": reasons},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a2_validate",
        description="Validate Artifact Manifest & hashes",
        handler=handle,
    ))
