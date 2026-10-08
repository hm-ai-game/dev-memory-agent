# Dev Memory Agent（开发记忆）

为 AI 编程助手保存**项目开发记忆**：把需求、实现、方案取舍和验证结果提炼为项目内的节点、进度与 Mermaid 流程图。记忆放在目标项目的 `.dev-memory/` 中，随项目代码一起交接；不会保存聊天原文。

## 能用在哪些 AI 平台

| 平台 | 使用方式 | 当前支持程度 |
| --- | --- | --- |
| OpenAI Codex（本地/桌面） | 安装插件，使用 skill 和生命周期 hook | 已实现并在本地验证 |
| Claude Code（本地 CLI） | 安装插件，使用 skill 和生命周期 hook | 插件格式与自动化测试已验证；仍建议在实际会话中试用 |
| 其他能运行命令的 AI 编程工具 | 让助手调用 `memory.py` CLI，或人工执行命令 | 手动集成；没有对应平台的自动 hook |
| 普通网页聊天（如 ChatGPT 或 Claude 网页聊天） | 无法直接访问本地项目文件 | 不支持直接安装或自动记录 |

运行环境：目标电脑需安装 Python 3.11+，并能用 `python` 命令启动。当前自动集成主要在 Windows 本地环境验证；其他系统请先检查 Python 命令与 hook 加载。

## 快速开始

先获取源码。以下命令从你存放项目的目录运行：

```bash
git clone https://github.com/quhaiming24-dev/dev-memory-agent.git
cd dev-memory-agent
```

为要记录的**目标项目**初始化一次（将路径和说明换成自己的）：

```bash
python memory.py init --project "C:\path\to\your-project" --name "我的项目" --goal "项目目标" --scope "当前范围"
```

该命令会创建目标项目的 `.dev-memory/`，并向其 `AGENTS.md` 加入项目级说明。已有记忆的项目无需重复初始化。建议将目标项目的 `.dev-memory/` 和 `AGENTS.md` 一起提交到目标项目仓库，以便其他开发者或 AI 助手接手；提交前自行检查其中是否含不适合公开的项目资料。

### 在 Codex 安装

从任意目录运行：

```bash
codex plugin marketplace add quhaiming24-dev/dev-memory-agent
```

然后在 Codex 桌面应用的 **Plugins Directory** 中找到 `Dev Memory (Local)`，安装 `dev-memory-agent`。在 Codex 中审核并信任 hook，重新开启目标项目会话。插件只在存在 `.dev-memory/project.json` 的项目中工作；未信任 hook 时仍可手动使用下面的 CLI 命令。

### 在 Claude Code 安装

从任意目录运行：

```bash
claude plugin marketplace add quhaiming24-dev/dev-memory-agent
claude plugin install dev-memory-agent@dev-memory-local
claude plugin list
```

在已初始化的目标项目中新开 Claude Code 会话。插件的 `SessionStart` 读取项目状态，`UserPromptSubmit` 为当前轮次生成 ID，`Stop` 检查是否记录了开发节点。Claude Code 的插件权限与 hook 信任由 Claude Code 管理。云端或远程 Claude Code 会话的插件加载尚未验证。

### 在其他 AI 编程工具中手动使用

让工具在目标项目里读 `AGENTS.md` 与 `.dev-memory/PROJECT.md`、`.dev-memory/STATUS.md`，并按 `skills/dev-memory/SKILL.md` 的规则，在完成实际开发工作后调用本仓库的 `memory.py`。这些平台不会自动触发本插件的 hook。

例如，从本仓库目录运行：

```bash
python memory.py status --project "C:\path\to\your-project"
python memory.py flow --project "C:\path\to\your-project"
python memory.py query "为什么选择" --project "C:\path\to\your-project"
python memory.py handoff --project "C:\path\to\your-project"
```

新增节点需先按 `skills/dev-memory/SKILL.md` 创建 UTF-8 JSON 输入文件，再执行：

```bash
python memory.py record --project "C:\path\to\your-project" --input "C:\path\to\your-project\.dev-memory\inbox\node.json"
```

已有节点可用 `revise --id <节点ID> --input <JSON文件>` 修订；旧版本会保留。

## 工作原理与验证

插件源码位于 `plugin.json`、`.claude-plugin/`、`skills/`、`hooks/` 与 `memory.py`。设计细节见 [架构文档](docs/ARCHITECTURE.md)。项目记忆位于每个目标项目自己的 `.dev-memory/` 中，彼此隔离。

```bash
python -m unittest discover -s tests -v
claude plugin validate ./ --strict
```

## 许可证

本项目以 [MIT License](LICENSE) 开源。任何人都可以查看、使用、修改和再发布，但须保留许可证与版权声明。
