---
name: dev-memory
description: Record and query durable development nodes in a Codex project that has .dev-memory/project.json. Use after implementing, testing, choosing, or rejecting an approach, and for project progress, rationale, flowchart, or handoff requests.
---

# Development memory

Use this skill only when the current project has `.dev-memory/project.json` or the user asks to enable development memory. This memory is project-scoped. The repository's `PROJECT.md` and `STATUS.md` under `.dev-memory/` are the starting context.

The plugin root is two directories above this SKILL.md; its `memory.py` is the CLI. The `UserPromptSubmit` hook also supplies an absolute command and turn id when this project is enabled.

After a Codex turn produces a durable development node, create a UTF-8 JSON input file in `.dev-memory/inbox/`, call `memory.py record --project <project-root> --input <input-file> --turn-id <turn-id>`, then remove the input file. Record separate nodes when multiple distinct outcomes occurred. Prefer a short title, an outcome with concrete validation, and explicit predecessors. Never copy the conversation or store raw prompts. Do not record ordinary discussion or speculative ideas as completed work; use `ack --turn-id` when no durable node occurred.

Node kinds: `requirement`, `milestone`, `decision`, `implementation`, `verification`, `failed_approach`, `blocker`, `direction_change`. Statuses: `planned`, `in_progress`, `completed`, `failed`, `blocked`, `superseded`. Evidence levels: `unverified`, `reported`, `observed`, `tested`. Use `tested` only when an actual test result was observed; user or assistant assertions without test output are `reported`.

For decisions, include `options`, `chosen_option`, and `rationale`; document why alternatives were not chosen. For failed approaches, include the failure outcome and what was learned. Use `predecessors` with existing node IDs to connect the flow. `source_ref` may identify a Codex task or commit, but not contain chat text. Use a stable `source_key` when retrying a write.

When a new requirement appears, record a `requirement` node, usually with `status: planned` and explicit `acceptance_criteria`. Link `predecessors` to the point in the project history where the requirement arose, and list earlier decisions or implementations it changes in `affects`. When implementation or testing progresses, revise the requirement status while retaining old revisions. Ordinary added requirements can be recorded automatically; a change to the project's overall goal or core architecture still needs user confirmation.

Set `impact: major` for project direction or core architecture changes. The CLI keeps these as `pending_approval` until `approved_by_user: true` is supplied from an actual user confirmation. Do not infer approval from an AI recommendation.

For progress, run `memory.py status`; for flowcharts, run `memory.py flow` (optionally `--phase`); for rationale, use `memory.py query`. `HANDOFF.md`, `PROJECT.md`, `STATUS.md`, `FLOW.md`, and `NODES.jsonl` belong to the target project and travel with it. Use the latest revision of each node ID when reading JSONL.

Input example (adjust to the real evidence):

```json
{
  "kind": "decision",
  "title": "Choose SQLite for first-phase memory storage",
  "summary": "The first phase stores project memory locally.",
  "phase": "Core memory",
  "status": "completed",
  "options": [
    {"name": "SQLite", "reason_for": "Local transactions and simple setup", "reason_against": "No built-in remote sync"},
    {"name": "Remote database", "reason_for": "Shared access", "reason_against": "Requires deployment and authentication"}
  ],
  "chosen_option": "SQLite",
  "rationale": "The first phase runs locally in Codex and needs no shared server.",
  "evidence_level": "reported",
  "source_ref": "Codex task or commit reference"
}
```
