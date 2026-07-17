"""Artifact Exchange：把跨 Agent artifact 通过 Master 校验后原子发布到 exchange/。

方案 5.2 / 12.1：
  exchange/manifests/*.json  # 每个交换包的元数据
  exchange/blobs/<sha256>/   # 按内容 hash 存储 blob（可硬链接/软链接指向原 artifact）
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dooragent.errors import DoorAgentError, ErrorCode


@dataclass(slots=True)
class ExchangeEntry:
    artifact_type: str
    source_path: str
    producer_agent_instance_id: str
    rtl_version_id: str | None
    workflow_id: str
    workflow_round_id: str
    hash: str = ""
    bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "source_path": self.source_path,
            "producer_agent_instance_id": self.producer_agent_instance_id,
            "rtl_version_id": self.rtl_version_id,
            "workflow_id": self.workflow_id,
            "workflow_round_id": self.workflow_round_id,
            "hash": self.hash,
            "bytes": self.bytes,
        }


class ExchangeManager:
    """
    workflow_root/exchange/
      manifests/<manifest_id>.json
      blobs/<sha256>/<basename>
    """

    def __init__(self, workflow_root: Path):
        self.root = Path(workflow_root).resolve() / "exchange"
        (self.root / "manifests").mkdir(parents=True, exist_ok=True)
        (self.root / "blobs").mkdir(parents=True, exist_ok=True)

    def publish(self, entries: list[ExchangeEntry]) -> dict[str, Any]:
        if not entries:
            raise DoorAgentError(ErrorCode.INVALID_REQUEST, "empty exchange entries")
        published = []
        for e in entries:
            src = Path(e.source_path)
            if not src.exists():
                raise DoorAgentError(ErrorCode.ARTIFACT_MISSING, f"source not found: {src}")
            digest = _sha256_file(src)
            expected_hash = e.hash
            if expected_hash and expected_hash != digest:
                raise DoorAgentError(
                    ErrorCode.ARTIFACT_HASH_MISMATCH,
                    f"hash mismatch for {src}: expected {expected_hash}, got {digest}",
                )
            e.hash = digest
            e.bytes = src.stat().st_size
            blob_dir = self.root / "blobs" / digest
            blob_dir.mkdir(parents=True, exist_ok=True)
            blob_path = blob_dir / src.name
            if not blob_path.exists():
                shutil.copy2(src, blob_path)
            published.append(e)

        manifest_id = f"xchg-{uuid.uuid4().hex[:12]}"
        manifest = {
            "manifest_id": manifest_id,
            "entries": [e.to_dict() for e in published],
            "created_at": time.time(),
        }
        target = self.root / "manifests" / f"{manifest_id}.json"
        tmp = target.with_suffix(".partial")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        try:
            with tmp.open("rb") as fh:
                os.fsync(fh.fileno())
        except OSError:  # pragma: no cover
            pass
        os.replace(tmp, target)
        return manifest

    def load_manifest(self, manifest_id: str) -> dict[str, Any]:
        p = self.root / "manifests" / f"{manifest_id}.json"
        if not p.exists():
            raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"exchange manifest not found: {manifest_id}")
        return json.loads(p.read_text(encoding="utf-8"))

    def list_manifests(self) -> list[str]:
        return sorted(p.stem for p in (self.root / "manifests").glob("*.json"))


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
