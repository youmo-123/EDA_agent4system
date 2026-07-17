"""Prompt / Skill 加载器：从 templates/ 读取 markdown，只做 IO 与最小校验。

- PromptLoader：按 role/name 加载 templates/prompts/<role>/<name>.md
- SkillLoader：按 role 加载 templates/skills/<role>/*/SKILL.md 并解析 YAML 头
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from dooragent.errors import DoorAgentError, ErrorCode


_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass(slots=True)
class Skill:
    role: str
    name: str
    path: str
    front_matter: dict
    body: str


class PromptLoader:
    def __init__(self, prompts_root: Path):
        self.root = prompts_root

    def load(self, role: str, name: str) -> str:
        path = self.root / role / f"{name}.md"
        if not path.exists():
            raise DoorAgentError(
                ErrorCode.INVALID_REQUEST,
                f"prompt not found: {path}",
            )
        return path.read_text(encoding="utf-8")


class SkillLoader:
    def __init__(self, skills_root: Path):
        self.root = skills_root

    def load_all(self, role: str) -> list[Skill]:
        role_dir = self.root / role
        if not role_dir.exists():
            return []
        skills: list[Skill] = []
        for sk_dir in sorted(role_dir.iterdir()):
            skill_md = sk_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            text = skill_md.read_text(encoding="utf-8")
            fm, body = _parse_front_matter(text)
            skills.append(Skill(
                role=role,
                name=sk_dir.name,
                path=str(skill_md),
                front_matter=fm,
                body=body,
            ))
        return skills


def _parse_front_matter(text: str) -> tuple[dict, str]:
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    fm_raw, body = m.group(1), m.group(2)
    # 极简 YAML 解析：只支持 key: value 与 key: []
    fm: dict = {}
    for line in fm_raw.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if v == "[]":
            fm[k.strip()] = []
        else:
            fm[k.strip()] = v
    return fm, body
