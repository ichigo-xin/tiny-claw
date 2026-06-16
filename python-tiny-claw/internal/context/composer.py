from __future__ import annotations

from pathlib import Path

from internal.context.skill import SkillLoader
from internal.schema.message import Message, Role


class PromptComposer:
    """负责根据工作区环境动态生成 System Prompt"""

    def __init__(self, work_dir: str):
        self.work_dir = work_dir
        self.skill_loader = SkillLoader(work_dir)

    def build(self) -> Message:
        parts: list[str] = []

        # 1. 极简内核 (Minimal Core)
        parts.append("""# 核心身份
你名叫 python-tiny-claw，一个由驾驭工程驱动的骨灰级研发助手。
你具备极简主义哲学，拒绝废话。你能通过系统提供的内置工具，创建、读取、修改和执行工作区中的代码。

# 核心纪律 (CRITICAL)
1. 如需检查文件是否存在，请使用 bash 的 ls 或 test -f，而不是对目录使用 read_file。
2. 创建新文件时，务必使用 write_file，并同时提供 path 和 content 参数。
3. 编辑文件前务必先读取现有文件，以理解上下文。
4. 无论何时你需要写代码或创建文件，都要直接使用 write_file 工具。
5. 遇到工具执行报错时，仔细阅读 stderr，尝试自己修正命令并重试。
6. 始终用中文回复，以便传达你的进展和想法。
""")

        # 2. 外部化状态：加载项目专属规范 (AGENTS.md)
        agents_md_path = Path(self.work_dir) / "AGENTS.md"
        if agents_md_path.is_file():
            try:
                content = agents_md_path.read_text(encoding="utf-8")
                parts.append("\n# 项目专属指南 (来自 AGENTS.md)")
                parts.append("以下是当前工作区特有的架构规范与注意事项，你的行为必须绝对符合以下要求：")
                parts.append("```markdown")
                parts.append(content)
                parts.append("```")
            except OSError:
                pass

        # 3. 动态加载技能外挂 (Skills)
        skills_content = self.skill_loader.load_all()
        if skills_content:
            parts.append(skills_content)

        return Message(
            role=Role.SYSTEM,
            content="\n".join(parts),
        )
