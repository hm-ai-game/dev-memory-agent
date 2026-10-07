# Dev Memory Agent

面向 Codex 和 Claude Code 的项目开发记忆。它把开发过程提炼为可交接的节点、进度和 Mermaid 流程图，不保存聊天原文。两个宿主共用目标项目的 `.dev-memory/`，不包含 UI。

项目需求增加时，Agent 可新增待开发需求节点，记录验收条件及受影响的旧方案；实施和验证后更新节点状态，保留之前的版本和开发路径。

## 位置

本文件夹是 Agent 源码。插件在所用宿主中安装；各目标项目在自己的 `.dev-memory/` 中保存记忆。详细设计见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 先在项目中启用

需要 Python 3.11 或更新版本。在 Agent 仓库中运行，以目标项目为例：

```powershell
python .\memory.py init --project E:\codex\my-project --name "我的项目" --goal "项目目标" --scope "当前范围"
```

该命令创建 `.dev-memory/`，并向目标项目的 `AGENTS.md` 添加一段项目级说明。已有 Codex 项目不需要重新 `init`，Claude Code 会读取同一份记忆。首次启用后，记忆会随目标项目一起交接。

## Codex 个人插件

插件内容位于本仓库的 `plugin.json`、`skills/` 和 `hooks/`。在 Agent 仓库中运行：

```powershell
codex plugin marketplace add .
codex plugin add dev-memory-agent@dev-memory-local
```

然后在 Codex 中审核、信任其 hook，并重新开始一个 Codex 会话。Codex 不会仅因安装插件而自动信任 hook。hook 只对已启用 `.dev-memory/project.json` 的项目工作；其他目录不记录。若插件未安装或 hook 未获信任，仍可手动使用 CLI，但自动补漏不会运行。

## Claude Code 版本

Claude Code 插件清单位于 `.claude-plugin/plugin.json`，使用相同的 `memory.py` 和 `skills/dev-memory/SKILL.md`，由 `hooks/claude_memory.py` 处理三个生命周期事件。需要本机可运行 `python`（3.11+）。

从本仓库目录安装本地市场及插件：

```powershell
claude plugin marketplace add ./
claude plugin install dev-memory-agent@dev-memory-local
claude plugin list
```

安装后在已执行 `init` 的目标项目启动新的 Claude Code 会话。`SessionStart` 注入项目状态，`UserPromptSubmit` 为本轮生成 ID 并提示记录，`Stop` 检查本轮是否执行过 `record` 或 `ack`。未启用开发记忆的项目不记录。也可以在开发时从目标项目运行 `claude --plugin-dir E:\codex\dev-memory-agent`，临时加载当前源码；不要同时使用临时加载和已安装插件，以免同一事件执行两次。

本地市场直接读取本仓库源码；移动或删除本仓库后需重新注册。Claude Code 插件设置和 hook 信任由 Claude Code 管理。当前没有在云端 Claude Code 会话中验证本地插件加载。

## 常用命令

```powershell
python .\memory.py status --project E:\codex\my-project
python .\memory.py flow --project E:\codex\my-project
python .\memory.py query "为什么选择" --project E:\codex\my-project
python .\memory.py handoff --project E:\codex\my-project
```

新增节点使用 UTF-8 JSON 文件：

```powershell
python .\memory.py record --project E:\codex\my-project --input E:\codex\my-project\.dev-memory\inbox\node.json
```

节点字段和审批规则见 `skills/dev-memory/SKILL.md`。已存在节点可通过 `revise --id <节点ID> --input <JSON文件>` 修订，旧版本保留。

## 验证

```powershell
python -m unittest discover -s tests -v
```
