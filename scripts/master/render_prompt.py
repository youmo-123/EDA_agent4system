#!/usr/bin/env python3
"""master_render_prompt：按角色/Skill/任务/约束渲染 Prompt。

- 不嵌入大产物、不嵌入密钥
- 只做字符串拼接与 hash 计算
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.atomic_io import write_json_atomic
from scripts.common.script_cli import ScriptResult, run_script
from dooragent.reports import PromptLoader, SkillLoader
from dooragent.runtime.secret_redactor import redact


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    role = params.get("role")
    prompt_name = params.get("prompt_name", "system")
    task_context = params.get("task_context", {})
    if not role:
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                             error={"message": "role is required"})
    prompt_root = REPO_ROOT / "templates" / "prompts"
    skills_root = REPO_ROOT / "templates" / "skills"
    try:
        base_prompt = PromptLoader(prompt_root).load(role, prompt_name)
    except Exception as exc:
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                             error={"message": str(exc)})
    skills = SkillLoader(skills_root).load_all(role)
    skill_summary = "\n".join(f"- {s.name}: {s.front_matter.get('description', '')}"
                              for s in skills)
    task_section = "\n".join(f"- {k}: {v!r}" for k, v in task_context.items())
    rendered = (
        f"{base_prompt}\n\n"
        f"## Skills available\n{skill_summary}\n\n"
        f"## Task context\n{task_section}\n"
    )
    rendered = redact(rendered)
    prompt_path = work_dir / "rendered-prompt.md"
    prompt_path.write_text(rendered, encoding="utf-8")
    h = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    write_json_atomic(work_dir / "prompt-manifest.json", {
        "role": role,
        "prompt_name": prompt_name,
        "prompt_path": prompt_path.name,
        "hash": h,
        "bytes": prompt_path.stat().st_size,
    })
    return ScriptResult(
        status="completed",
        output_artifact_refs=["rendered-prompt.md", "prompt-manifest.json"],
        raw_metrics={"prompt_hash": h, "prompt_bytes": prompt_path.stat().st_size},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="master_render_prompt",
        description="Render role/skill/task prompt with hash",
        handler=handle,
    ))
