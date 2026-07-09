from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class Skill:
    name: str = "Unknown Skill"
    description: str = "No description provided."
    body: str = ""


class SkillLoader:
    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def load_all(self) -> str:
        skill_base_dir = Path(self.work_dir) / ".claw" / "skills"
        if not skill_base_dir.exists():
            return ""

        skills_content = []
        skills_content.append("\n### 可用专业技能 (Agent Skills)\n")
        skills_content.append("以下是你拥有的标准化外挂技能，请在符合 description 描述的场景下严格遵循其正文指令：\n\n")

        for skill_md_path in skill_base_dir.rglob("SKILL.md"):
            try:
                content = skill_md_path.read_text(encoding="utf-8")
                skill = self._parse_skill_md(content)
                skills_content.append(f"#### 技能名称: {skill.name}\n")
                skills_content.append(f"**触发条件**: {skill.description}\n\n")
                skills_content.append("**执行指南**:\n")
                skills_content.append(skill.body)
                skills_content.append("\n\n---\n")
            except Exception:
                pass

        full_content = "".join(skills_content)
        if len(full_content) < 100:
            return ""
        return full_content

    def _parse_skill_md(self, content: str) -> Skill:
        skill = Skill(body=content)

        if content.startswith("---\n") or content.startswith("---\r\n"):
            parts = content.split("---", 2)
            if len(parts) == 3:
                frontmatter = parts[1]
                skill.body = parts[2].strip()
                lines = frontmatter.split("\n")
                for line in lines:
                    line = line.strip()
                    if line.startswith("name:"):
                        skill.name = line[len("name:"):].strip()
                    elif line.startswith("description:"):
                        skill.description = line[len("description:"):].strip()
        return skill
