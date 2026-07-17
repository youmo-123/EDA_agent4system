"""崩溃恢复：扫描 workflow 目录并恢复 stale claim / partial 写入。

策略：
- .partial 文件：如果对应正式文件已存在则删除；否则也删除（未发布视作无副作用）
- claimed/<worker>/*.json：若 worker 不在存活列表则回退到 ready/
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from dooragent.events.bus import FileEventBus


class Recoverer:
    def __init__(self, workflow_root: Path):
        self.root = Path(workflow_root).resolve()

    def cleanup_partials(self) -> int:
        cnt = 0
        for p in self.root.rglob("*.partial"):
            try:
                p.unlink()
                cnt += 1
            except OSError:
                pass
        return cnt

    def recover_event_claims(self, workers_alive: Iterable[str]) -> int:
        bus = FileEventBus(self.root)
        return bus.recover_stale_claims(workers_alive)

    def scan_state(self) -> dict[str, int]:
        state_dir = self.root / "workflow" / "state" / "snapshots"
        counts = {"snapshots": 0, "transitions": 0}
        if state_dir.exists():
            counts["snapshots"] = sum(1 for _ in state_dir.rglob("*.json"))
        trans_dir = self.root / "workflow" / "state" / "transitions"
        if trans_dir.exists():
            counts["transitions"] = sum(1 for _ in trans_dir.rglob("*.json"))
        return counts
