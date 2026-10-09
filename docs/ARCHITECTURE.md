# 开发记忆 Agent：框架

## 目标与边界

此 Agent 在 Codex 和 Claude Code 中运行。它从开发和验证过程提炼新增需求、关键节点、技术决策、失败路径和阶段进度，供后续查询、流程图和项目交接使用。另提供本机只读网页仪表盘，用于跨项目宇宙总览和单项目星云探索。普通网页聊天平台不在当前集成范围。记忆按项目隔离，不存储对话原文。

Agent 源码与个人安装包放在本仓库。目标项目首次启用后，项目自己的 `.dev-memory/` 是可交接的正式记录。下一位开发者仅需获得目标项目及其 `.dev-memory/`；无需获得本机其他项目的记忆。

## 运行流程

1. `init` 为目标项目建立项目身份、目标和范围，写入 `AGENTS.md` 的简短说明。
2. Codex 或 Claude Code 的 `SessionStart` hook 提供当前状态；`UserPromptSubmit` hook 为本轮注入记录规则及 turn ID。Claude Code 适配器在项目 `.runtime/` 中为每次提交生成 turn ID，仅保存 ID，不保存提示词。
3. Agent 开发、验证或比较方案时，在结束前把稳定结论写成 JSON 节点，调用 CLI 保存；没有节点时调用 `ack`。
4. `Stop` hook 检查本轮是否已记录或确认无节点；若未处理，仅要求 Agent 再检查一次。它不自行臆测测试结论，也不持久保存聊天记录。
5. 写入节点后自动生成 `STATUS.md`、`FLOW.md`、`HANDOFF.md`。这些文件随项目交接。

Hook 触发与信任设置属于各自宿主环境。插件必须安装并信任其 hook 后，自动补漏流程才会运行；目标项目的 `AGENTS.md` 为项目级辅助约束。Codex 和 Claude Code 适配器共享 `memory.py`、Skill 与项目数据格式。

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

## 本地仪表盘

`memory.py dashboard` 启动仅监听 `127.0.0.1` 的 Python 标准库 HTTP 服务，提供同源静态页面和只读项目数据接口。右侧工具栏的状态、流程、时间线和搜索从现有项目数据生成。宇宙总览通过本机项目路径列表逐个读取 `.dev-memory/`；列表仅保存路径，不集中复制节点。项目管理可注册或移除列表项，移除不会操作项目记忆。首页使用用户选定且未经修改的四星云图片，画布仅遮盖图中少量示例文字，网页导航与前四个项目标签显示可交互的真实内容；未注册位置禁用，第五个及后续项目按顺序分配到四片星云上的可滚动标签组，标签同样显示真实项目名和记忆数。图片缩放保持长宽比并限制平移；有留白时使用原图派生的透明边缘渐隐到黑色星空，不改原始图片文件。单项目星云继续由粒子、渐变与尘埃纹理实时绘制；有效节点单独绘制成亮星，节点类型、影响级别和状态决定大小与亮度。`predecessors` 和 `affects` 对应的关系线默认可见，选中节点后高亮相连的线。浏览器不加载外部脚本或字体；首页只加载同源参考图。

## 交接约定

交接顺序：`HANDOFF.md` → `PROJECT.md` → `STATUS.md` → `FLOW.md` → 按需查询 `NODES.jsonl`。如果生成文件缺失，可以从 `project.json` 和 `NODES.jsonl` 重新生成。下一位开发者应能说明项目方向、当前进展、主要方案取舍、验证等级和下一步。

## 第一阶段验收

- 一个项目首次启用后，Codex 或 Claude Code 开发回合能自动提醒记录或确认无新节点。
- 方案选择节点保留备选方案与未选理由；验证节点区分声称与实测。
- 重要变更在用户确认前不改变项目方向。
- 两个项目的记忆完全隔离；导出其中一个项目不会带上另一个项目内容。
- 可生成状态、流程图与交接入口，下一位开发者不依赖原聊天记录就能继续工作。
