"""Resource Lease Scheduler：预算/并发/lease 管理。

约束（方案 11.4/1.2 节）：
- max_parallel_agent_instances
- max_parallel_a1_instances
- max_parallel_a3_evaluations
- max_parallel_synthesis_jobs
- CPU / memory 预算
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class LeaseState(StrEnum):
    REQUESTED = "REQUESTED"
    QUEUED = "QUEUED"
    GRANTED = "GRANTED"
    ACTIVE = "ACTIVE"
    RELEASING = "RELEASING"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


@dataclass(slots=True)
class Lease:
    lease_id: str
    resource_pool: str          # e.g. "a1_instance" / "a3_evaluation" / "synthesis_job"
    owner: str
    state: LeaseState
    granted_at: float | None = None
    expires_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "resource_pool": self.resource_pool,
            "owner": self.owner,
            "state": self.state.value,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
        }


class LeaseScheduler:
    """线程安全的内存 Lease Scheduler。

    使用池化上限，不足时进入 QUEUED；lease 到期未续约则回收。
    """

    def __init__(self, pool_limits: dict[str, int], *, default_lease_s: float = 600.0):
        self._limits = dict(pool_limits)
        self._default_lease_s = default_lease_s
        self._active: dict[str, list[Lease]] = {k: [] for k in pool_limits}
        self._queue: dict[str, list[Lease]] = {k: [] for k in pool_limits}
        self._lock = threading.RLock()

    def request(
        self,
        *,
        resource_pool: str,
        owner: str,
        lease_s: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Lease:
        if resource_pool not in self._limits:
            raise ValueError(f"unknown resource pool: {resource_pool}")
        lease = Lease(
            lease_id=f"lease-{uuid.uuid4().hex[:12]}",
            resource_pool=resource_pool,
            owner=owner,
            state=LeaseState.REQUESTED,
            metadata=metadata or {},
        )
        with self._lock:
            self._reclaim_expired_locked()
            if len(self._active[resource_pool]) < self._limits[resource_pool]:
                self._grant_locked(lease, lease_s)
            else:
                lease.state = LeaseState.QUEUED
                self._queue[resource_pool].append(lease)
        return lease

    def renew(self, lease_id: str, lease_s: float | None = None) -> Lease | None:
        with self._lock:
            for pool_leases in self._active.values():
                for lease in pool_leases:
                    if lease.lease_id == lease_id and lease.state == LeaseState.ACTIVE:
                        lease.expires_at = time.time() + (lease_s or self._default_lease_s)
                        return lease
        return None

    def release(self, lease_id: str) -> Lease | None:
        with self._lock:
            for pool, pool_leases in self._active.items():
                for lease in pool_leases:
                    if lease.lease_id == lease_id:
                        lease.state = LeaseState.RELEASED
                        pool_leases.remove(lease)
                        self._try_promote_locked(pool)
                        return lease
        return None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._reclaim_expired_locked()
            return {
                pool: {
                    "limit": self._limits[pool],
                    "active": [l.to_dict() for l in self._active[pool]],
                    "queued": [l.to_dict() for l in self._queue[pool]],
                }
                for pool in self._limits
            }

    # ------------------------------------------------------------------ #
    def _grant_locked(self, lease: Lease, lease_s: float | None) -> None:
        lease.state = LeaseState.ACTIVE
        lease.granted_at = time.time()
        lease.expires_at = lease.granted_at + (lease_s or self._default_lease_s)
        self._active[lease.resource_pool].append(lease)

    def _reclaim_expired_locked(self) -> None:
        now = time.time()
        for pool, active in self._active.items():
            expired = [l for l in active if l.expires_at and l.expires_at <= now]
            for l in expired:
                l.state = LeaseState.EXPIRED
                active.remove(l)
            for _ in expired:
                self._try_promote_locked(pool)

    def _try_promote_locked(self, pool: str) -> None:
        while self._queue[pool] and len(self._active[pool]) < self._limits[pool]:
            queued = self._queue[pool].pop(0)
            self._grant_locked(queued, None)
