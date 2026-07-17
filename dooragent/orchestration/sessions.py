"""Agent Session 注册与管理。

Session 与 Agent Instance 一一对应；同轮次内不改 session_id。
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Session:
    session_id: str
    agent_role: str
    agent_instance_id: str
    workflow_id: str
    workflow_round_id: str
    started_at: float = 0.0
    attempt_id: int = 0
    iteration_id: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_role": self.agent_role,
            "agent_instance_id": self.agent_instance_id,
            "workflow_id": self.workflow_id,
            "workflow_round_id": self.workflow_round_id,
            "started_at": self.started_at,
            "attempt_id": self.attempt_id,
            "iteration_id": self.iteration_id,
            "metadata": self.metadata,
        }


class SessionRegistry:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    def create(self, *, agent_role: str, agent_instance_id: str,
               workflow_id: str, workflow_round_id: str) -> Session:
        session = Session(
            session_id=f"ses-{uuid.uuid4().hex[:12]}",
            agent_role=agent_role,
            agent_instance_id=agent_instance_id,
            workflow_id=workflow_id,
            workflow_round_id=workflow_round_id,
            started_at=time.time(),
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def bump_attempt(self, session_id: str) -> Session:
        with self._lock:
            s = self._sessions[session_id]
            s.attempt_id += 1
            return s

    def bump_iteration(self, session_id: str) -> Session:
        with self._lock:
            s = self._sessions[session_id]
            s.iteration_id += 1
            return s

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def list_by_role(self, role: str) -> list[Session]:
        return [s for s in self._sessions.values() if s.agent_role == role]
