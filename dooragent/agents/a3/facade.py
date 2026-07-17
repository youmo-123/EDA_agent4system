from __future__ import annotations
from typing import Any
from dooragent.agents.contracts import AgentResult, AgentTask
from dooragent.agents.a3.agent import A3Agent
from dooragent.agents.a3.context import A3Context


class A3Facade:
    def __init__(self, context: A3Context, agent: A3Agent | None = None):
        self.ctx = context
        self.agent = agent or A3Agent(
            registry=context.tool_registry,
            product_run_root=context.product_run_root,
        )

    def execute(self, task: AgentTask | dict[str, Any]) -> AgentResult:
        if isinstance(task, dict):
            task = AgentTask.from_dict(task)
        return self.agent.execute(task)
