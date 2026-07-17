"""Scheduler：把 Master 决策的 Agent Task 分发到目标 Agent Facade。

- 输入：Agent Task Envelope + budget/priority
- 输出：ScheduleDecision（agent_role、target_instance、lease_id、rank）
- 通过 LeaseScheduler 申请资源、按优先级排序、遵守并发上限

本模块不直接执行 Task；执行由 WorkflowController + Agent Facade 完成。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dooragent.orchestration.leases import LeaseScheduler, Lease, LeaseState


@dataclass(slots=True)
class ScheduleDecision:
    task_id: str
    agent_role: str
    lease: Lease | None
    granted: bool
    reason: str


class Scheduler:
    """内存调度器；配合文件 Case Queue 实现持久化。"""

    ROLE_TO_POOL = {
        "A1": "a1_instance",
        "A2": "agent_instance",
        "A3": "agent_instance",
        "MASTER": "agent_instance",
    }

    def __init__(self, leases: LeaseScheduler):
        self.leases = leases

    def schedule(self, task: dict[str, Any]) -> ScheduleDecision:
        role = str(task.get("agent_role", "")).upper()
        pool = self.ROLE_TO_POOL.get(role, "agent_instance")
        try:
            lease = self.leases.request(
                resource_pool=pool,
                owner=task.get("task_id", "unknown-task"),
                metadata={"role": role, "operation": task.get("operation", "")},
            )
        except ValueError as exc:
            return ScheduleDecision(
                task_id=task.get("task_id", ""),
                agent_role=role,
                lease=None,
                granted=False,
                reason=str(exc),
            )
        return ScheduleDecision(
            task_id=task.get("task_id", ""),
            agent_role=role,
            lease=lease,
            granted=lease.state == LeaseState.ACTIVE,
            reason="granted" if lease.state == LeaseState.ACTIVE else "queued",
        )


# ---------------------------------------------------------------------------- #
# Manifest 中 master_schedule_task 的 entrypoint 引用点（builtin tool）：
# ---------------------------------------------------------------------------- #
def schedule_task(task: dict[str, Any], *, leases: LeaseScheduler | None = None) -> dict[str, Any]:
    """将 task 交给全局 Scheduler，返回 ScheduleDecision 的字典视图。"""
    if leases is None:
        # 单元测试友好：使用一个最小池
        leases = LeaseScheduler({"agent_instance": 4, "a1_instance": 2})
    scheduler = Scheduler(leases)
    decision = scheduler.schedule(task)
    return {
        "task_id": decision.task_id,
        "agent_role": decision.agent_role,
        "granted": decision.granted,
        "reason": decision.reason,
        "lease": decision.lease.to_dict() if decision.lease else None,
    }


def health() -> dict[str, Any]:
    return {"state": "HEALTHY", "component": "scheduler"}
