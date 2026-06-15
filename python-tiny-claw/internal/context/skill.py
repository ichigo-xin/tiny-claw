from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Skill:
    name: str = "Unknown Skill"
    description: str = "No description provided."
    body: str = ""


class SkillLoader:
    """负责从本地文件系统中加载并解析符合规范的技能模板"""

    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def load_all(self) -> str:
        skill_base_dir = Path(self.work_dir) / ".claw" / "skills"

        if not skill_base_dir.is_dir():
            return ""

        parts: list[str] = [
            "\n### 可用专业技能 (Agent Skills)",
            "以下是你拥有的标准化外挂技能，请在符合 description 描述的场景下严格遵循其正文指令：\n",
        ]

        for skill_md in skill_base_dir.rglob("SKILL.md"):
            try:
                content = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue

            skill = _parse_skill_md(content)

            parts.append(f"#### 技能名称: {skill.name}")
            parts.append(f"**触发条件**: {skill.description}\n")
            parts.append("**执行指南**:\n")
            parts.append(skill.body)
            parts.append("\n\n---")

        if len(parts) < 4:
            return ""

        return "\n".join(parts)


def _parse_skill_md(content: str) -> Skill:
    skill = Skill(body=content)

    stripped = content.lstrip()
    if not stripped.startswith("---"):
        return skill

    # 以 --- 分割，最多分 3 段
    segments = stripped.split("---", 2)
    if len(segments) != 3:
        return skill

    frontmatter = segments[1]
    skill.body = segments[2].strip()

    for line in frontmatter.splitlines():
        line = line.strip()
        if line.startswith("name:"):
            skill.name = line[len("name:"):].strip()
        elif line.startswith("description:"):
            skill.description = line[len("description:"):].strip()

    return skill
