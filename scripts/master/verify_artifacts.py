#!/usr/bin/env python3
"""master_verify_artifacts：校验 producer / 版本 / hash / 路径 / 必需证据。"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.artifact_io import sha256_file
from scripts.common.script_cli import ScriptResult, run_script
from dooragent.agents.master.evidence import EvidenceReviewer


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    entries = params.get("entries") or []
    reviewer = EvidenceReviewer()
    review = reviewer.review_manifest(entries)
    hash_reasons: list[str] = []
    for i, e in enumerate(entries):
        path = e.get("path")
        expected_hash = e.get("hash")
        if path and expected_hash:
            p = Path(path)
            if not p.exists():
                hash_reasons.append(f"entry[{i}] path not found: {path}")
                continue
            actual = sha256_file(p)
            if actual != expected_hash:
                hash_reasons.append(f"entry[{i}] hash mismatch: expected {expected_hash} got {actual}")
    reasons = review.reasons + hash_reasons
    ok = not reasons
    return ScriptResult(
        status="completed" if ok else "failed",
        error_code=None if ok else "SCHEMA_MISMATCH",
        raw_metrics={"ok": ok, "reasons": reasons, "entries": len(entries)},
        error=None if ok else {"reasons": reasons},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="master_verify_artifacts",
        description="Verify artifact producer/version/hash/path/binding",
        handler=handle,
    ))
