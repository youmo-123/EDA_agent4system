"""Hook 注册与触发：确定性监测器，不拥有业务决策。

状态机（方案 8.2）：
  DISABLED / ARMED / OBSERVING / TRIGGERED / ESCALATING / COOLDOWN / DEGRADED
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable


class HookState(StrEnum):
    DISABLED = "DISABLED"
    ARMED = "ARMED"
    OBSERVING = "OBSERVING"
    TRIGGERED = "TRIGGERED"
    ESCALATING = "ESCALATING"
    COOLDOWN = "COOLDOWN"
    DEGRADED = "DEGRADED"


class HookLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(slots=True)
class HookTrigger:
    hook_id: str
    level: HookLevel
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)
    at: float = 0.0


@dataclass(slots=True)
class Hook:
    hook_id: str
    predicate: Callable[[dict[str, Any]], bool]
    level: HookLevel
    reason: str
    cooldown_s: float = 30.0
    state: HookState = HookState.ARMED
    last_triggered_at: float = 0.0


class HookRegistry:
    """内存 Hook 注册中心；按事件触发并做冷却抑制。"""

    def __init__(self):
        self._hooks: dict[str, Hook] = {}
        self._history: list[HookTrigger] = []

    def register(self, hook: Hook) -> None:
        self._hooks[hook.hook_id] = hook

    def disable(self, hook_id: str) -> None:
        if hook_id in self._hooks:
            self._hooks[hook_id].state = HookState.DISABLED

    def enable(self, hook_id: str) -> None:
        if hook_id in self._hooks:
            self._hooks[hook_id].state = HookState.ARMED

    def observe(self, event: dict[str, Any]) -> list[HookTrigger]:
        """把 event 送到所有 ARMED/OBSERVING 状态的 Hook，返回被触发的列表。"""
        triggers: list[HookTrigger] = []
        now = time.time()
        for hook in self._hooks.values():
            if hook.state in (HookState.DISABLED, HookState.COOLDOWN):
                if hook.state == HookState.COOLDOWN and (now - hook.last_triggered_at) >= hook.cooldown_s:
                    hook.state = HookState.ARMED
                else:
                    continue
            hook.state = HookState.OBSERVING
            try:
                if hook.predicate(event):
                    hook.state = HookState.TRIGGERED
                    hook.last_triggered_at = now
                    trig = HookTrigger(
                        hook_id=hook.hook_id,
                        level=hook.level,
                        reason=hook.reason,
                        payload={"event": event},
                        at=now,
                    )
                    triggers.append(trig)
                    self._history.append(trig)
                    if hook.level == HookLevel.HIGH:
                        hook.state = HookState.ESCALATING
                    else:
                        hook.state = HookState.COOLDOWN
                else:
                    hook.state = HookState.ARMED
            except Exception:
                hook.state = HookState.DEGRADED
        return triggers

    def history(self) -> list[HookTrigger]:
        return list(self._history)

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "hook_id": h.hook_id,
                "level": h.level.value,
                "state": h.state.value,
                "last_triggered_at": h.last_triggered_at,
            }
            for h in self._hooks.values()
        ]
