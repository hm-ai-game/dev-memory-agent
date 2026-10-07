# Dev Memory Agent

面向 Codex 的项目开发记忆。它把开发过程提炼为可交接的节点、进度和 Mermaid 流程图，不保存聊天原文。第一阶段只支持 Codex，不包含 UI。

## 位置

本文件夹是 Agent 源码。插件在 Codex 中个人安装一次；各目标项目在自己的 `.dev-memory/` 中保存记忆。详细设计见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 先在项目中启用

需要 Python 3.11 或更新版本。在 Agent 仓库中运行，以目标项目为例：

```powershell
python .\memory.py init --project E:\codex\my-project --name "我的项目" --goal "项目目标" --scope "当前范围"
```

该命令创建 `.dev-memory/`，并向目标项目的 `AGENTS.md` 添加一段项目级说明。首次启用后，记忆会随目标项目一起交接。

## Codex 个人插件

插件内容位于本仓库的 `plugin.json`、`skills/` 和 `hooks/`。在 Agent 仓库中运行：

```powershell
codex plugin marketplace add .
codex plugin add dev-memory-agent@dev-memory-local
```

然后在 Codex 中审核、信任其 hook，并重新开始一个 Codex 会话。Codex 不会仅因安装插件而自动信任 hook。hook 只对已启用 `.dev-memory/project.json` 的项目工作；其他目录不记录。若插件未安装或 hook 未获信任，仍可手动使用 CLI，但自动补漏不会运行。

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
