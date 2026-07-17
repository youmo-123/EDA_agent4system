"""Agent Task / Result / ArtifactRef 契约（与 interfaces/agents/*.schema.json 对齐）。"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal


AgentRole = Literal["MASTER", "A1", "A2", "A3"]


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentResultStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    WAITING_GATE2 = "waiting_gate2"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"


class CapabilityState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(slots=True)
class ArtifactRef:
    uri: str
    artifact_hash: str | None = None
    schema_ref: str | None = None
    producer: str | None = None
    rtl_version_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentTask:
    workflow_id: str
    workflow_round_id: str
    agent_role: AgentRole
    operation: str
    rtl_version_id: str | None = None
    input_artifact_refs: list[dict[str, Any]] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    budget: dict[str, Any] = field(default_factory=dict)
    requested_outputs: list[str] = field(default_factory=list)
    reply_to: str = "master"
    schema_version: str = "1.0"
    interface_version: str = "1.0"
    task_id: str = field(default_factory=lambda: _uid("task"))
    idempotency_key: str = field(default_factory=lambda: _uid("idem"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentTask":
        allowed = {"workflow_id", "workflow_round_id", "agent_role", "operation",
                   "rtl_version_id", "input_artifact_refs", "constraints", "budget",
                   "requested_outputs", "reply_to", "schema_version",
                   "interface_version", "task_id", "idempotency_key"}
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass(slots=True)
class AgentResult:
    task_id: str
    agent_instance_id: str
    status: AgentResultStatus
    output_artifact_refs: list[dict[str, Any]] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    capability_state: CapabilityState = CapabilityState.HEALTHY
    suggested_next_actions: list[dict[str, Any]] = field(default_factory=list)
    error: dict[str, Any] | None = None
    agent_role: str = ""
    schema_version: str = "1.0"
    interface_version: str = "1.0"
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["capability_state"] = self.capability_state.value
        return data
