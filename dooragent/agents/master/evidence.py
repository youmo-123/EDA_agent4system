"""EvidenceReviewer：校验跨 Agent artifact 的通用绑定字段与 hash。

方案 5.2：所有产物必须绑定 workflow_id / round / rtl_version_id / producer /
schema_version / artifact_hash / created_at。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dooragent.errors import DoorAgentError, ErrorCode


@dataclass(slots=True)
class ReviewResult:
    ok: bool
    reasons: list[str]


# artifact_hash 是权威字段名；hash 是常见简写；两者接受其一
REQUIRED_BINDING = (
    "workflow_id",
    "producer_agent_instance_id",
    "schema_version",
    "created_at",
)


class EvidenceReviewer:
    def review_manifest(self, entries: list[dict[str, Any]]) -> ReviewResult:
        reasons: list[str] = []
        for i, e in enumerate(entries):
            for f in REQUIRED_BINDING:
                if not e.get(f):
                    reasons.append(f"entry[{i}] missing binding: {f}")
            if not (e.get("artifact_hash") or e.get("hash")):
                reasons.append(f"entry[{i}] missing binding: artifact_hash|hash")
        return ReviewResult(ok=not reasons, reasons=reasons)

    def verify_hash(self, source_path: Path, expected: str) -> bool:
        h = hashlib.sha256()
        with source_path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        if h.hexdigest() != expected:
            raise DoorAgentError(
                ErrorCode.ARTIFACT_HASH_MISMATCH,
                f"hash mismatch for {source_path}",
            )
        return True
