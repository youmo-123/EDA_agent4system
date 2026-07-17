"""事件信封与路由校验。

方案 9.1 节路由矩阵：
  source=A1|A2|A3 → recipient 只能是 master 或本实例 observer
  source=master   → recipient 可以是 A1|A2|A3|hook|observer
  source=hook     → 只能提醒当前实例或升级到 master
违反矩阵的事件应进入死信并记录 ROUTING_POLICY_VIOLATION。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from dooragent.errors import DoorAgentError, ErrorCode

_ALLOWED_SOURCES = {"master", "A1", "A2", "A3", "hook", "supervisor", "tool"}
_ALLOWED_RECIPIENTS = {"master", "A1", "A2", "A3", "hook", "observer"}


@dataclass(slots=True)
class Event:
    schema_version: str
    event_id: str
    workflow_id: str
    source: str
    recipient: str
    kind: str
    created_at: str
    workflow_round_id: str | None = None
    rtl_version_id: str | None = None
    correlation_id: str | None = None
    caused_by: str | None = None
    artifact_refs: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "workflow_id": self.workflow_id,
            "workflow_round_id": self.workflow_round_id,
            "rtl_version_id": self.rtl_version_id,
            "source": self.source,
            "recipient": self.recipient,
            "kind": self.kind,
            "correlation_id": self.correlation_id,
            "caused_by": self.caused_by,
            "artifact_refs": self.artifact_refs,
            "payload": self.payload,
            "created_at": self.created_at,
        }


def build_event(
    *,
    workflow_id: str,
    source: str,
    recipient: str,
    kind: str,
    workflow_round_id: str | None = None,
    rtl_version_id: str | None = None,
    correlation_id: str | None = None,
    caused_by: str | None = None,
    artifact_refs: list[str] | None = None,
    payload: dict[str, Any] | None = None,
) -> Event:
    if source not in _ALLOWED_SOURCES:
        raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"invalid source: {source}")
    if recipient not in _ALLOWED_RECIPIENTS:
        raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"invalid recipient: {recipient}")
    validate_routing(source=source, recipient=recipient)
    return Event(
        schema_version="1.0",
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        workflow_id=workflow_id,
        workflow_round_id=workflow_round_id,
        rtl_version_id=rtl_version_id,
        source=source,
        recipient=recipient,
        kind=kind,
        correlation_id=correlation_id,
        caused_by=caused_by,
        artifact_refs=list(artifact_refs or []),
        payload=dict(payload or {}),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def validate_routing(*, source: str, recipient: str) -> None:
    """路由矩阵硬校验；不合法直接抛 ROUTING_POLICY_VIOLATION。"""
    if source in {"A1", "A2", "A3"}:
        if recipient not in {"master", "observer"}:
            raise DoorAgentError(
                ErrorCode.ROUTING_POLICY_VIOLATION,
                f"role agent {source} cannot send to {recipient}",
            )
    elif source == "hook":
        if recipient not in {"master", "A1", "A2", "A3", "observer"}:
            raise DoorAgentError(
                ErrorCode.ROUTING_POLICY_VIOLATION,
                f"hook cannot send to {recipient}",
            )
    # master / supervisor / tool 可以发给任意 allowed recipient
