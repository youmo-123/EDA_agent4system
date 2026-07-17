"""MasterAgent：Master 的推理循环。

Master 不生成 EDA 业务证据；operations 全部是控制面 Tool（master_* 系列）。
"""
from __future__ import annotations

from dooragent.agents.base import BaseAgent


class MasterAgent(BaseAgent):
    role = "MASTER"
    operations = {
        "plan_workflow": ["master_schedule_task"],
        "route_task": ["master_schedule_task"],
        "review_evidence": ["master_verify_artifacts"],
        "resolve_gate": ["master_resolve_gate"],
        "review_round": ["master_verify_artifacts"],
        "publish_report": ["master_publish_outputs"],
        "materialize_exchange": ["master_materialize_exchange"],
        "archive_round": ["master_archive_round"],
        "create_workspace": ["master_create_workspace"],
        # health 由 BaseAgent 短路
    }
