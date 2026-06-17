# tiny-claw 工作区说明

本工作区用于学习「驾驭工程 (Harness Engineering) / Agent Harness」理念，包含同一套微型 AI Agent 引擎的两种语言实现。

## 一、项目用途

这是一个用于**学习**的项目。核心目标是从零理解并实现一个极简的 AI Agent 操作系统（Harness），理解如何调度工具、管理上下文、安全拦截，而不是仅仅调用大模型 API。

## 二、目录结构与双语言关系

工作区下存在两个**严格对应**的子项目：

| 子项目 | 作用 | 语言 | 来源 |
| --- | --- | --- | --- |
| `go-tiny-claw/` | **主干 / 教程跟随实现**，按教程一节一节补充代码 | Go | 跟随极客时间专栏《从零构建 Agent Harness》（作者：Tony Bai）逐节实现 |
| `python-tiny-claw/` | **镜像实现**，与 Go 版本功能保持一致 | Python | 对应 Go 版本手工移植 |

> 入口：Go 为 `go-tiny-claw/cmd/claw/main.go`；Python 为 `python-tiny-claw/main.py`。

### 模块对应表（Go ↔ Python）

| 职责 | Go 路径 | Python 路径 |
| --- | --- | --- |
| 程序入口 | `cmd/claw/main.go` | `main.py` |
| 主循环 / ReAct 引擎 | `internal/engine/loop.go` | `internal/engine/loop.py` |
| 事件上报 | `internal/engine/reporter.go`、`terminal_reporter.go` | `internal/engine/reporter.py`、`terminal_reporter.py` |
| 会话 / 上下文管理 | `internal/context/session.go`、`compactor.go`、`composer.go` | `internal/engine/session.py`、`internal/context/composer.py`（session 在 engine 下，compactor 逻辑并入 composer/session） |
| Skill 加载 | `internal/context/skill.go` | `internal/context/skill.py` |
| 模型 Provider | `internal/provider/interface.go`、`openai.go`、`claude.go` | `internal/provider/interface.py`、`openai.py`、`claude.py` |
| 消息 Schema | `internal/schema/message.go` | `internal/schema/message.py` |
| 工具注册与实现 | `internal/tools/registry.go` 及 `read_file/write_file/edit_file/bash/powershell.go` | `internal/tools/registry.py` 及对应同名 `.py` |
| 飞书集成 | `internal/feishu/bot.go` | `internal/feishu/bot.py` |

> 两个子项目各自也存在自己的 `AGENTS.md`（语言特定的约束）。本文件为工作区顶层规则，优先级最高。

## 三、核心工作流：双语言同步（最重要）

**每当 `go-tiny-claw/` 中的 Go 代码发生变更（新增章节 / 修改逻辑 / 修复 bug），必须同步修改 `python-tiny-claw/` 中对应的 Python 代码，使两者行为保持一致。**

执行同步时遵循：

1. **先读懂 Go 改动**：理解本节教程引入的概念、数据结构、控制流，再动手。
2. **按模块对应表定位** Python 文件；若 Go 新增了模块（如新工具、新 provider），在 Python 侧创建对应文件并补齐 `__init__.py` 导出。
3. **保持语言习惯**：
   - Go 的 `interface` ↔ Python 的抽象基类 / Protocol；Go 的 `struct` ↔ Python 的 `dataclass`。
   - Go 的 `goroutine/channel` ↔ Python 的 `threading/queue` 或 `asyncio`，按原实现就近选择。
   - 错误处理：Go 的 `error` 返回值 ↔ Python 的异常 `raise/try`。
4. **命名风格转换**：Go 的 `PascalCase`（导出）↔ Python 的 `snake_case`；工厂函数 `NewXxxTool` ↔ `new_xxx_tool`。
5. **完成后自检**：确认两侧模块一一对应、导出符号齐全、运行入口能跑通同样的演示流程。

> 如果某节 Go 改动属于纯 Go 生态（如 `go.mod` 依赖），Python 侧对应处理依赖（`requirements.txt`）即可，不必逐行翻译。

## 四、运行环境

- 模型：默认使用智谱 GLM（`glm-4.5-air`），通过 `ZHIPU_API_KEY` 环境变量或各子项目根目录 `.env` 文件配置。
- 平台：Windows 开发环境。命令执行工具按系统注册：Windows 用 `powershell` 工具，其他平台用 `bash` 工具。
- 工具原语仅保留图灵完备的最小集：`read_file`、`write_file`、`edit_file`、命令执行（`bash`/`powershell`）。
- 状态外部化：记忆与计划持久化在 `PLAN.md` / `TODO.md` 等文件中，不在内存里维护状态机。

## 五、通用约定（适用于两个子项目）

- 所有 API 接口返回 JSON，且包含 `code` 与 `message` 字段。
- 所有错误处理必须返回**中文**报错信息，禁止英文抛错。
- **禁止删除各子项目根目录下的任何文件**（如 `a.txt`、`b.txt`、`c.txt`、`hello.txt` 等，它们是教程演示用的探针 / 测试文件）。
- Python 文件中，除条件导入与动态导入外，所有 `import` 语句必须放在文件顶部。

## 六、给后续对话的快速上手提示

- 用户说「跟着教程更新了 Go」或「这一节我改了 xxx」时，默认任务 = **同步对应的 Python 代码**。
- 改动前先用本文件的「模块对应表」定位两侧文件，再读两侧当前实现做差异比对。
- 优先编辑既有文件，不要随意新建文件；只有当 Go 侧确实新增了模块时，才在 Python 侧创建对应文件。
