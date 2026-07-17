"""文件系统事件总线：write .partial → fsync → atomic rename → dead-letter。

目录布局（相对 workflow root）：
  workflow/events/
    tmp/                          # 未发布的 .partial 文件
    ready/                        # 已发布可消费
    claimed/<worker_id>/          # 已被 Consumer 认领
    dead-letter/                  # ROUTING_POLICY_VIOLATION 或反复失败
    processed/                    # Consumer 处理完毕后归档
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Iterable

from dooragent.errors import DoorAgentError, ErrorCode
from dooragent.events.envelope import Event, validate_routing

_SUBDIRS = ("tmp", "ready", "claimed", "dead-letter", "processed")


class FileEventBus:
    def __init__(self, workflow_root: Path):
        self.workflow_root = Path(workflow_root).resolve()
        self._events_root = self.workflow_root / "workflow" / "events"
        for sub in _SUBDIRS:
            (self._events_root / sub).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    def publish(self, event: Event) -> Path:
        try:
            validate_routing(source=event.source, recipient=event.recipient)
        except DoorAgentError:
            return self._dead_letter(event, reason="routing")
        filename = f"{event.created_at.replace(':', '-')}_{event.event_id}.json"
        tmp = self._events_root / "tmp" / filename
        target = self._events_root / "ready" / filename
        _atomic_write_json(tmp, target, event.to_dict())
        return target

    def list_ready(self) -> list[Path]:
        return sorted((self._events_root / "ready").glob("*.json"))

    def claim(self, path: Path, worker_id: str) -> Path:
        if not path.exists():
            raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"event not exists: {path}")
        claim_dir = self._events_root / "claimed" / worker_id
        claim_dir.mkdir(parents=True, exist_ok=True)
        target = claim_dir / path.name
        os.replace(path, target)
        return target

    def mark_processed(self, path: Path) -> Path:
        target = self._events_root / "processed" / path.name
        os.replace(path, target)
        return target

    def dead_letter(self, path: Path, reason: str) -> Path:
        if not path.exists():
            raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"event not exists: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_dead_letter_reason"] = reason
        data["_dead_letter_at"] = time.time()
        target = self._events_root / "dead-letter" / path.name
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
        path.unlink()
        return target

    def recover_stale_claims(self, worker_ids_alive: Iterable[str]) -> int:
        """把不活跃 worker 的 claimed/ 文件放回 ready/。"""
        alive = set(worker_ids_alive)
        restored = 0
        claimed_root = self._events_root / "claimed"
        if not claimed_root.exists():
            return 0
        for worker_dir in claimed_root.iterdir():
            if not worker_dir.is_dir() or worker_dir.name in alive:
                continue
            for f in worker_dir.glob("*.json"):
                os.replace(f, self._events_root / "ready" / f.name)
                restored += 1
            try:
                worker_dir.rmdir()
            except OSError:
                pass
        return restored

    # ------------------------------------------------------------------ #
    def _dead_letter(self, event: Event, reason: str) -> Path:
        target = self._events_root / "dead-letter" / f"{event.event_id}.json"
        payload = event.to_dict()
        payload["_dead_letter_reason"] = reason
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return target


def _atomic_write_json(tmp: Path, target: Path, data) -> None:
    tmp.parent.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        with tmp.open("rb") as fh:
            os.fsync(fh.fileno())
    except OSError:  # pragma: no cover
        pass
    os.replace(tmp, target)
    try:
        dir_fd = os.open(str(target.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:  # pragma: no cover
        pass
