# 开发记忆 Agent：第一阶段框架

## 目标与边界

此 Agent 在 Codex 中运行。它从开发和验证过程提炼新增需求、关键节点、技术决策、失败路径和阶段进度，供后续查询、流程图和项目交接使用。普通 ChatGPT 聊天与 Work 不纳入第一阶段。记忆按项目隔离，不存储对话原文，也不提供 UI。

Agent 源码与个人安装包放在本仓库。目标项目首次启用后，项目自己的 `.dev-memory/` 是可交接的正式记录。下一位开发者仅需获得目标项目及其 `.dev-memory/`；无需获得本机其他项目的记忆。

## 运行流程

1. `init` 为目标项目建立项目身份、目标和范围，写入 `AGENTS.md` 的简短说明。
2. Codex 的 `SessionStart` hook 提供当前状态；`UserPromptSubmit` hook 为本轮注入记录规则及 turn ID。
3. Codex 开发、验证或比较方案时，在结束前把稳定结论写成 JSON 节点，调用 CLI 保存；没有节点时调用 `ack`。
4. `Stop` hook 检查本轮是否已记录或确认无节点；若未处理，仅要求 Codex 再检查一次。它不自行臆测测试结论，也不持久保存聊天记录。
5. 写入节点后自动生成 `STATUS.md`、`FLOW.md`、`HANDOFF.md`。这些文件随项目交接。

Codex 的 hook 触发与信任设置属于宿主环境。插件必须安装并信任其 hook 后，自动补漏流程才会运行；目标项目的 `AGENTS.md` 为项目级辅助约束。

## 数据结构

`.dev-memory/project.json`：`schema_version`、`project_id`、名称、目标、范围、创建时间。

`.dev-memory/NODES.jsonl`：每行一个完整节点版本，追加写入。同一 `id` 以最后的 `revision` 为当前值；旧版本保留。字段包括：

| 字段 | 作用 |
| --- | --- |
| `kind`、`title`、`summary`、`phase`、`status` | 节点内容与阶段 |
| `options`、`chosen_option`、`rationale` | 方案取舍及原因 |
| `outcome`、`evidence_level`、`evidence` | 实施和验证结果 |
| `predecessors`、`affects`、`next_steps` | 流程关系、受新需求影响的旧节点及进度 |
| `acceptance_criteria` | 新需求的验收条件 |
| `source_ref`、`source_key` | 可追溯引用和幂等写入键 |
| `impact`、`approved_by_user`、`project_update` | 重要变更审批与项目方向更新 |

`evidence_level` 含 `unverified`、`reported`、`observed`、`tested`。只有真正观察到测试结果才用 `tested`。改变项目方向或重大架构的节点，在确认前保持 `pending_approval`，不更新项目方向。

## 存储与查询

项目文件是正式来源；查询从 JSONL 重建当前节点，支持关键词、节点类型、阶段过滤。首版采用线性扫描，适合本地项目规模；以后可增加 SQLite 全文索引作为可重建缓存，不改变交接格式。`FLOW.md` 用节点的 `predecessors` 关系生成 Mermaid 图，并按阶段分组；决策节点在图中显示选择及简短理由，图下列出各备选方案的完整取舍；新增需求可用虚线标明对旧节点的影响。也可用 CLI 生成单阶段图。

`.runtime/`、`inbox/` 和写入锁被项目内 `.gitignore` 排除。运行时标记只包含 turn ID 和处理结果。聊天内容只在 Codex 当前上下文中用于提炼节点，不写入项目记忆。

## 交接约定

交接顺序：`HANDOFF.md` → `PROJECT.md` → `STATUS.md` → `FLOW.md` → 按需查询 `NODES.jsonl`。如果生成文件缺失，可以从 `project.json` 和 `NODES.jsonl` 重新生成。下一位开发者应能说明项目方向、当前进展、主要方案取舍、验证等级和下一步。

## 第一阶段验收

- 一个项目首次启用后，Codex 开发回合能自动提醒记录或确认无新节点。
- 方案选择节点保留备选方案与未选理由；验证节点区分声称与实测。
- 重要变更在用户确认前不改变项目方向。
- 两个项目的记忆完全隔离；导出其中一个项目不会带上另一个项目内容。
- 可生成状态、流程图与交接入口，下一位开发者不依赖原聊天记录就能继续工作。
