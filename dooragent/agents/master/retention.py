"""RetentionPolicy：轮次归档、artifact 保留与清理策略。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RetentionPolicy:
    keep_workflow_days: int = 30
    keep_intermediate_days: int = 7
    keep_dead_letter_days: int = 90
    freeze_on_terminal: bool = True

    def should_freeze(self, lifecycle_state: str) -> bool:
        return self.freeze_on_terminal and lifecycle_state in {"COMPLETED", "FAILED", "CANCELLED"}
