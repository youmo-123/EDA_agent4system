"""dooragent 唯一产品入口。

命令：
  dooragent run     --request <request.json>          # 创建新 workflow
  dooragent resume  --workflow <workflow_id>          # 恢复
  dooragent status  --workflow <workflow_id>          # 查看状态
  dooragent cancel  --workflow <workflow_id>          # 取消

内部辅助（不作为产品对外语义，仅用于调试）：
  dooragent list-tools                                # 列出所有已注册 Tool 与状态
  dooragent dispatch-task --workflow <id> --task <t>  # 手动派发一个 Agent Task
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from dooragent.bootstrap import bootstrap


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dooragent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="create a new DoorAgent workflow")
    p_run.add_argument("--request", required=True, help="request JSON path")
    p_run.add_argument("--workflow-id", help="explicit workflow_id; default auto-generated")

    p_status = sub.add_parser("status", help="show workflow status")
    p_status.add_argument("--workflow", required=True)

    p_resume = sub.add_parser("resume", help="resume workflow")
    p_resume.add_argument("--workflow", required=True)

    p_cancel = sub.add_parser("cancel", help="cancel workflow")
    p_cancel.add_argument("--workflow", required=True)

    p_tools = sub.add_parser("list-tools", help="list registered tools and health states")

    p_dispatch = sub.add_parser("dispatch-task",
                                 help="internal: dispatch one agent task JSON to Master facade")
    p_dispatch.add_argument("--workflow", required=True)
    p_dispatch.add_argument("--task", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    br = bootstrap()

    if args.command == "run":
        request = _read_json(Path(args.request))
        workflow_id = args.workflow_id or f"dooragent-run-{uuid.uuid4().hex[:8]}"
        controller = br.orchestration.create(workflow_id, request,
                                              budget=request.get("budget"))
        result = {
            "workflow_id": workflow_id,
            "status": "CREATED",
            "master_workspace": (br.product_run_root / "runs" / workflow_id /
                                 "workspaces" / "r-1" / "master").as_posix(),
        }
    elif args.command == "status":
        controller = br.orchestration.get(args.workflow)
        result = controller.status()
    elif args.command == "cancel":
        controller = br.orchestration.get(args.workflow)
        result = controller.cancel()
    elif args.command == "resume":
        # 恢复：重新加载 controller 并触发 recovery 扫描
        controller = br.orchestration.get(args.workflow)
        counts = controller.recovery.scan_state()
        restored = controller.recovery.recover_event_claims(workers_alive={"master"})
        cleaned = controller.recovery.cleanup_partials()
        result = {
            "workflow_id": args.workflow,
            "status": "RESUMED",
            "state_counts": counts,
            "events_restored": restored,
            "partials_cleaned": cleaned,
        }
    elif args.command == "list-tools":
        result = {
            "count": len(br.tool_registry.list_ids()),
            "tools": br.tool_registry.health_all(),
        }
    elif args.command == "dispatch-task":
        task = _read_json(Path(args.task))
        agent_result = br.master_facade.execute(task)
        result = agent_result.to_dict()
    else:
        raise AssertionError(args.command)

    _print_json(result)
    return 0


def _read_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
