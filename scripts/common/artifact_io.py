"""artifact_io：相对路径 artifact 读写与 hash。"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_posix_rel(path: Path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        raise ValueError(f"{path} not under {root}")


def build_artifact_ref(
    *,
    artifact_type: str,
    path: Path,
    workflow_id: str,
    producer_agent_instance_id: str,
    workflow_round_id: str | None = None,
    rtl_version_id: str | None = None,
    schema_version: str = "1.0",
) -> dict[str, Any]:
    """返回带通用绑定字段的 artifact 引用（不写盘）。"""
    p = Path(path)
    return {
        "artifact_type": artifact_type,
        "path": p.as_posix(),
        "hash": sha256_file(p),
        "bytes": p.stat().st_size,
        "workflow_id": workflow_id,
        "workflow_round_id": workflow_round_id,
        "rtl_version_id": rtl_version_id,
        "producer_agent_instance_id": producer_agent_instance_id,
        "schema_version": schema_version,
        "created_at": now_iso(),
    }
