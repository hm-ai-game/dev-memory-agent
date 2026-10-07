#!/usr/bin/env python3
"""Project-local, portable development memory for Codex.

Only distilled development facts are stored. Conversation transcripts are never
copied into the project memory directory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEMORY_DIR = ".dev-memory"
SCHEMA_VERSION = 1
KINDS = {
    "requirement", "milestone", "decision", "implementation", "verification",
    "failed_approach", "blocker", "direction_change",
}
STATUSES = {
    "planned", "in_progress", "completed", "failed", "blocked",
    "superseded", "pending_approval",
}
EVIDENCE_LEVELS = {"unverified", "reported", "observed", "tested"}
MANAGED_START = "<!-- dev-memory-agent:start -->"
MANAGED_END = "<!-- dev-memory-agent:end -->"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def write_text_atomic(path: Path, value: str) -> None:
    temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def find_project(start: Path) -> Path | None:
    location = start.resolve()
    if location.is_file():
        location = location.parent
    for candidate in (location, *location.parents):
        if (candidate / MEMORY_DIR / "project.json").is_file():
            return candidate
    return None


def require_project(path: Path | None) -> Path:
    root = find_project(path or Path.cwd())
    if root is None:
        raise ValueError("当前目录尚未启用开发记忆。请先运行 init。")
    return root


class DirectoryLock:
    def __init__(self, path: Path, timeout: float = 5.0):
        self.path = path
        self.timeout = timeout

    def __enter__(self) -> "DirectoryLock":
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.path.mkdir()
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"项目记忆正在被其他进程写入：{self.path}")
                time.sleep(0.05)

    def __exit__(self, *_: object) -> None:
        self.path.rmdir()


def load_nodes(root: Path) -> dict[str, dict[str, Any]]:
    path = root / MEMORY_DIR / "NODES.jsonl"
    nodes: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return nodes
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"NODES.jsonl 第 {number} 行无效：{exc}") from exc
            if item.get("schema_version") != SCHEMA_VERSION:
                raise ValueError(f"NODES.jsonl 第 {number} 行的 schema_version 不受支持")
            nodes[item["id"]] = item
    return nodes


def _string(value: Any, field: str, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{field} 必须是字符串")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{field} 不能为空")
    return value


def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ValueError(f"{field} 必须是字符串数组")
    return [x.strip() for x in value if x.strip()]


def normalize_node(data: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("节点输入必须是 JSON 对象")
    forbidden = {"conversation", "transcript", "messages", "raw_chat", "prompt"}
    if forbidden.intersection(data):
        raise ValueError("节点输入包含对话原文类字段；只保存提炼后的开发结论")
    allowed = {
        "id", "kind", "title", "summary", "phase", "status", "impact",
        "options", "chosen_option", "rationale", "outcome", "evidence_level",
        "evidence", "predecessors", "affects", "acceptance_criteria", "next_steps", "source_ref", "source_key",
        "approved_by_user", "occurred_at", "project_update",
    }
    unknown = set(data) - allowed
    if unknown:
        raise ValueError("未知节点字段：" + ", ".join(sorted(unknown)))
    merged = {**(existing or {}), **data}
    kind = _string(merged.get("kind"), "kind", True)
    default_status = "planned" if kind == "requirement" else "completed"
    status = _string(merged.get("status", default_status), "status", True)
    level = _string(merged.get("evidence_level", "unverified"), "evidence_level", True)
    if kind not in KINDS:
        raise ValueError(f"未知 kind：{kind}")
    if status not in STATUSES:
        raise ValueError(f"未知 status：{status}")
    if level not in EVIDENCE_LEVELS:
        raise ValueError(f"未知 evidence_level：{level}")
    impact = _string(merged.get("impact", "normal"), "impact", True)
    if impact not in {"normal", "major"}:
        raise ValueError("impact 只能是 normal 或 major")
    options = merged.get("options", [])
    if not isinstance(options, list) or any(not isinstance(x, dict) for x in options):
        raise ValueError("options 必须是对象数组")
    normalized_options = []
    for option in options:
        normalized_options.append({
            "name": _string(option.get("name"), "options.name", True),
            "reason_for": _string(option.get("reason_for"), "options.reason_for"),
            "reason_against": _string(option.get("reason_against"), "options.reason_against"),
        })
    chosen_option = _string(merged.get("chosen_option"), "chosen_option")
    rationale = _string(merged.get("rationale"), "rationale")
    if kind == "decision":
        if not normalized_options or not chosen_option or not rationale:
            raise ValueError("decision 节点必须包含 options、chosen_option 和 rationale")
        if chosen_option not in {option["name"] for option in normalized_options}:
            raise ValueError("chosen_option 必须匹配 options 中的方案名称")
    evidence = merged.get("evidence", [])
    if not isinstance(evidence, list) or any(not isinstance(x, dict) for x in evidence):
        raise ValueError("evidence 必须是对象数组")
    normalized_evidence = []
    for item in evidence:
        normalized_evidence.append({
            "type": _string(item.get("type"), "evidence.type", True),
            "ref": _string(item.get("ref"), "evidence.ref"),
            "result": _string(item.get("result"), "evidence.result", True),
        })
    approved = merged.get("approved_by_user", False)
    if not isinstance(approved, bool):
        raise ValueError("approved_by_user 必须是布尔值")
    project_update = merged.get("project_update", {})
    if not isinstance(project_update, dict) or set(project_update) - {"goal", "scope"}:
        raise ValueError("project_update 只能包含 goal 或 scope")
    if project_update and kind != "direction_change":
        raise ValueError("只有 direction_change 可更新项目方向")
    project_update = {key: _string(value, f"project_update.{key}") for key, value in project_update.items()}
    if (kind == "direction_change" or impact == "major") and not approved:
        status = "pending_approval"
    elif approved and status == "pending_approval":
        status = "completed"
    created = existing.get("created_at") if existing else now()
    revision = existing.get("revision", 0) + 1 if existing else 1
    item_id = existing["id"] if existing else _string(data.get("id"), "id") or uuid.uuid4().hex[:12]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", item_id):
        raise ValueError("id 只能包含字母、数字、下划线和连字符，最长 64 位")
    return {
        "schema_version": SCHEMA_VERSION,
        "id": item_id,
        "revision": revision,
        "kind": kind,
        "title": _string(merged.get("title"), "title", True),
        "summary": _string(merged.get("summary"), "summary", True),
        "phase": _string(merged.get("phase", "未分阶段"), "phase", True),
        "status": status,
        "impact": impact,
        "options": normalized_options,
        "chosen_option": chosen_option,
        "rationale": rationale,
        "outcome": _string(merged.get("outcome"), "outcome"),
        "evidence_level": level,
        "evidence": normalized_evidence,
        "predecessors": _string_list(merged.get("predecessors"), "predecessors"),
        "affects": _string_list(merged.get("affects"), "affects"),
        "acceptance_criteria": _string_list(merged.get("acceptance_criteria"), "acceptance_criteria"),
        "next_steps": _string_list(merged.get("next_steps"), "next_steps"),
        "source_ref": _string(merged.get("source_ref"), "source_ref"),
        "source_key": _string(merged.get("source_key"), "source_key"),
        "approved_by_user": approved,
        "project_update": project_update,
        "occurred_at": _string(merged.get("occurred_at"), "occurred_at") or now(),
        "created_at": created,
        "updated_at": now(),
    }


def append_node(root: Path, data: dict[str, Any], *, revise_id: str | None = None) -> dict[str, Any]:
    memory = root / MEMORY_DIR
    with DirectoryLock(memory / ".write-lock"):
        nodes = load_nodes(root)
        if revise_id and revise_id not in nodes:
            raise ValueError(f"找不到节点 {revise_id}")
        existing = nodes.get(revise_id) if revise_id else None
        source_key = data.get("source_key")
        if source_key and not revise_id:
            for item in nodes.values():
                if item.get("source_key") == source_key:
                    return item
        item = normalize_node(data, existing=existing)
        if not revise_id and item["id"] in nodes:
            raise ValueError(f"节点 ID 已存在：{item['id']}")
        for predecessor in item["predecessors"]:
            if predecessor == item["id"] or predecessor not in nodes:
                raise ValueError(f"无效的前置节点：{predecessor}")
        for affected in item["affects"]:
            if affected == item["id"] or affected not in nodes:
                raise ValueError(f"无效的受影响节点：{affected}")
        with (memory / "NODES.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        nodes[item["id"]] = item
        if item["kind"] == "direction_change" and item["approved_by_user"] and item["project_update"]:
            project = read_json(memory / "project.json")
            project.update(item["project_update"])
            project["updated_at"] = now()
            write_json_atomic(memory / "project.json", project)
        refresh(root, nodes)
        return item


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_project(project: dict[str, Any]) -> str:
    return (
        f"# {project['name']}\n\n"
        f"项目 ID：`{project['project_id']}`\n\n"
        f"## 目标\n\n{project['goal'] or '待明确'}\n\n"
        f"## 范围与约束\n\n{project['scope'] or '待明确'}\n\n"
        "项目方向由项目负责人确认。开发节点见 `NODES.jsonl`，当前状态见 `STATUS.md`。\n"
    )


def render_status(project: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> str:
    ordered = sorted(nodes.values(), key=lambda x: (x["occurred_at"], x["created_at"]))
    active = [n for n in ordered if n["status"] not in {"superseded", "pending_approval"}]
    done = [n for n in active if n["status"] == "completed"]
    doing = [n for n in active if n["status"] == "in_progress"]
    blocked = [n for n in active if n["status"] == "blocked"]
    planned = [n for n in active if n["status"] == "planned"]
    pending = [n for n in ordered if n["status"] == "pending_approval"]
    started = [n for n in active if n["status"] in {"completed", "in_progress", "blocked"}]
    phase = started[-1]["phase"] if started else "尚未开始"
    lines = [
        f"# {project['name']}：当前状态", "",
        f"最近更新：{max((n['updated_at'] for n in ordered), default=project['created_at'])}", "",
        f"当前阶段：**{phase}**", "",
        f"节点概况：已完成 {len(done)}，进行中 {len(doing)}，待开发 {len(planned)}，受阻 {len(blocked)}，待确认 {len(pending)}。", "",
        "## 最近完成", "",
    ]
    lines.extend(f"- `{n['id']}` {_md(n['title'])}（{n['evidence_level']}）" for n in done[-8:])
    if not done:
        lines.append("- 暂无")
    lines.extend(["", "## 进行中与阻碍", ""])
    lines.extend(f"- `{n['id']}` {_md(n['title'])}：{n['status']}" for n in doing + blocked)
    if not doing and not blocked:
        lines.append("- 暂无")
    lines.extend(["", "## 待开发需求", ""])
    requirements = [n for n in planned if n["kind"] == "requirement"]
    lines.extend(f"- `{n['id']}` {_md(n['title'])}：{_md(n['summary'])}" for n in requirements)
    if not requirements:
        lines.append("- 暂无")
    lines.extend(["", "## 下一步", ""])
    has_successor = {predecessor for n in active for predecessor in n["predecessors"]}
    leaves = [n for n in active if n["id"] not in has_successor]
    next_steps = list(dict.fromkeys(step for n in leaves for step in n["next_steps"]))
    lines.extend(f"- {_md(step)}" for step in next_steps[-10:])
    if not next_steps:
        lines.append("- 尚未记录")
    lines.extend(["", "## 待确认的重要变更", ""])
    lines.extend(f"- `{n['id']}` {_md(n['title'])}" for n in pending)
    if not pending:
        lines.append("- 暂无")
    return "\n".join(lines) + "\n"


def _mermaid_label(value: str) -> str:
    return re.sub(r"[\[\]{}<>\"|]", "", value).replace("\n", " ")[:72]


def render_flow(project: dict[str, Any], nodes: dict[str, dict[str, Any]], phase: str | None = None) -> str:
    ordered = sorted(nodes.values(), key=lambda x: (x["occurred_at"], x["created_at"]))
    if phase:
        ordered = [n for n in ordered if n["phase"] == phase]
    lines = [f"# {project['name']}：开发流程", "", "图中的虚线表示未采用或失败的路径。", "", "```mermaid", "flowchart TD"]
    if not ordered:
        lines.append('    empty["尚无开发节点"]')
    ids = {n["id"]: f"n{index}" for index, n in enumerate(ordered)}
    phases = list(dict.fromkeys(n["phase"] for n in ordered))
    for index, phase_name in enumerate(phases):
        lines.append(f'    subgraph p{index}["{_mermaid_label(phase_name)}"]')
        for n in ordered:
            if n["phase"] == phase_name:
                label = _mermaid_label(n["title"])
                if n["kind"] == "decision":
                    choice = _mermaid_label(n["chosen_option"])[:36]
                    reason = _mermaid_label(n["rationale"])[:48]
                    label += f"<br/>选择：{choice}<br/>原因：{reason}"
                lines.append(f'        {ids[n["id"]]}["{label}<br/>{n["status"]}"]')
        lines.append("    end")
    for n in ordered:
        for predecessor in n["predecessors"]:
            if predecessor in ids and predecessor not in n.get("affects", []):
                arrow = "-.->" if n["kind"] == "failed_approach" or n["status"] == "failed" else "-->"
                lines.append(f'    {ids[predecessor]} {arrow} {ids[n["id"]]}')
        for affected in n.get("affects", []):
            if affected in ids:
                lines.append(f'    {ids[affected]} -. 新需求影响 .-> {ids[n["id"]]}')
    lines.extend(["```", "", "## 节点索引", ""])
    for n in ordered:
        lines.append(f"- `{n['id']}` [{n['phase']}] {n['title']} — {n['status']}")
    decisions = [n for n in ordered if n["kind"] == "decision"]
    lines.extend(["", "## 方案选择与原因", ""])
    if not decisions:
        lines.append("暂无决策节点。")
    for n in decisions:
        lines.extend([
            f"### `{n['id']}` {_md(n['title'])}", "",
            f"- 选择：{_md(n['chosen_option'])}",
            f"- 选择原因：{_md(n['rationale'])}",
        ])
        for option in n["options"]:
            lines.append(
                f"- 方案 {_md(option['name'])}：可取之处 {_md(option['reason_for']) or '未记录'}；"
                f"顾虑 {_md(option['reason_against']) or '未记录'}"
            )
        if n["outcome"]:
            lines.append(f"- 后续结果：{_md(n['outcome'])}")
        lines.append("")
    requirements = [n for n in ordered if n["kind"] == "requirement"]
    lines.extend(["", "## 新增需求与验收", ""])
    if not requirements:
        lines.append("暂无需求节点。")
    for n in requirements:
        lines.extend([
            f"### `{n['id']}` {_md(n['title'])}", "",
            f"- 内容：{_md(n['summary'])}",
            f"- 状态：{n['status']}",
        ])
        if n.get("affects"):
            lines.append(f"- 影响旧节点：{', '.join('`' + item + '`' for item in n['affects'])}")
        for criterion in n.get("acceptance_criteria", []):
            lines.append(f"- 验收条件：{_md(criterion)}")
        lines.append("")
    return "\n".join(lines) + "\n"


def render_handoff(project: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> str:
    return (
        f"# {project['name']}：交接入口\n\n"
        "请先读 `PROJECT.md` 了解目标，再读 `STATUS.md` 了解当前进度。"
        "需要追溯方案取舍时查询 `NODES.jsonl`；需要整体路径时读 `FLOW.md`。\n\n"
        "`NODES.jsonl` 每行是一个节点版本；同一 ID 以最高 revision 为准。"
        "历史版本保留，以便了解决策如何变化。\n\n"
        f"项目 ID：`{project['project_id']}`。当前有效节点：{len(nodes)}。\n\n"
        "记录仅包含提炼的开发节点，不包含 Codex 对话原文。"
        "证据等级分别为 unverified、reported、observed、tested；"
        "不要把 reported 当作测试通过。\n"
    )


def refresh(root: Path, nodes: dict[str, dict[str, Any]] | None = None) -> None:
    memory = root / MEMORY_DIR
    project = read_json(memory / "project.json")
    nodes = nodes if nodes is not None else load_nodes(root)
    write_text_atomic(memory / "PROJECT.md", render_project(project))
    write_text_atomic(memory / "STATUS.md", render_status(project, nodes))
    write_text_atomic(memory / "FLOW.md", render_flow(project, nodes))
    write_text_atomic(memory / "HANDOFF.md", render_handoff(project, nodes))


def install_agents_note(root: Path) -> None:
    path = root / "AGENTS.md"
    note = (
        f"{MANAGED_START}\n"
        "## Development memory\n\n"
        "This project uses `.dev-memory/` for durable development nodes. "
        "At the start of work, read `.dev-memory/PROJECT.md` and `.dev-memory/STATUS.md`. "
        "Before finishing a Codex turn that implements, verifies, rejects, or chooses a development approach, "
        "use the installed `dev-memory` skill to record concise structured nodes. "
        "Do not store conversation transcripts. Obtain user confirmation before approving "
        "a major architectural or project-direction change.\n"
        f"{MANAGED_END}\n"
    )
    if path.exists():
        content = path.read_text(encoding="utf-8")
        if MANAGED_START in content:
            return
        path.write_text(content.rstrip() + "\n\n" + note, encoding="utf-8")
    else:
        path.write_text(note, encoding="utf-8")


def initialize(root: Path, name: str, goal: str, scope: str) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"项目文件夹不存在：{root}")
    memory = root / MEMORY_DIR
    if (memory / "project.json").exists():
        raise ValueError(f"该项目已启用开发记忆：{memory}")
    memory.mkdir(parents=True, exist_ok=True)
    project = {
        "schema_version": SCHEMA_VERSION,
        "project_id": uuid.uuid4().hex,
        "name": name.strip() or root.name,
        "goal": goal.strip(),
        "scope": scope.strip(),
        "created_at": now(),
    }
    write_json_atomic(memory / "project.json", project)
    (memory / "NODES.jsonl").touch()
    (memory / "inbox").mkdir(exist_ok=True)
    (memory / ".gitignore").write_text(".runtime/\n.write-lock/\ninbox/\n", encoding="utf-8")
    install_agents_note(root)
    refresh(root, {})
    return project


def mark_turn(root: Path, turn_id: str, result: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", turn_id):
        raise ValueError("turn_id 格式无效")
    marker = root / MEMORY_DIR / ".runtime" / "turns" / (turn_id + ".json")
    write_json_atomic(marker, {"turn_id": turn_id, "result": result, "recorded_at": now()})


def query_nodes(nodes: dict[str, dict[str, Any]], text: str, kind: str | None, phase: str | None, limit: int) -> list[dict[str, Any]]:
    terms = [term.casefold() for term in text.split() if term.strip()]
    matches = []
    for n in nodes.values():
        if kind and n["kind"] != kind:
            continue
        if phase and n["phase"] != phase:
            continue
        haystack = " ".join([
            n["title"], n["summary"], n["rationale"], n["outcome"],
            n["chosen_option"], *n["next_steps"], *n.get("acceptance_criteria", []),
            *(" ".join(o.values()) for o in n["options"]),
        ]).casefold()
        if all(term in haystack for term in terms):
            score = sum(3 if term in n["title"].casefold() else 1 for term in terms)
            matches.append((score, n))
    matches.sort(key=lambda pair: (pair[0], pair[1]["updated_at"]), reverse=True)
    return [n for _, n in matches[:limit]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex 开发节点记忆")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="在项目中启用记忆")
    init.add_argument("--project", type=Path, default=Path.cwd())
    init.add_argument("--name", required=True)
    init.add_argument("--goal", default="")
    init.add_argument("--scope", default="")
    for command in ("record", "revise"):
        p = sub.add_parser(command, help="新增或修订开发节点")
        p.add_argument("--project", type=Path)
        p.add_argument("--input", required=True, type=Path, help="UTF-8 JSON 节点文件")
        p.add_argument("--turn-id")
        if command == "revise":
            p.add_argument("--id", required=True)
    ack = sub.add_parser("ack", help="本轮无开发节点")
    ack.add_argument("--project", type=Path)
    ack.add_argument("--turn-id", required=True)
    query = sub.add_parser("query", help="查询开发节点")
    query.add_argument("text", nargs="?", default="")
    query.add_argument("--project", type=Path)
    query.add_argument("--kind", choices=sorted(KINDS))
    query.add_argument("--phase")
    query.add_argument("--limit", type=int, default=20)
    for command in ("status", "flow", "handoff", "refresh"):
        p = sub.add_parser(command)
        p.add_argument("--project", type=Path)
        if command == "flow":
            p.add_argument("--phase")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            project = initialize(args.project, args.name, args.goal, args.scope)
            print(json.dumps({"project_id": project["project_id"], "path": str(args.project.resolve() / MEMORY_DIR)}, ensure_ascii=False))
            return 0
        root = require_project(args.project)
        memory = root / MEMORY_DIR
        if args.command in {"record", "revise"}:
            data = read_json(args.input)
            node = append_node(root, data, revise_id=args.id if args.command == "revise" else None)
            if args.turn_id:
                mark_turn(root, args.turn_id, "recorded")
            print(json.dumps({"id": node["id"], "revision": node["revision"], "status": node["status"]}, ensure_ascii=False))
        elif args.command == "ack":
            mark_turn(root, args.turn_id, "no_node")
            print("本轮已标记为无开发节点")
        elif args.command == "query":
            result = query_nodes(load_nodes(root), args.text, args.kind, args.phase, max(1, args.limit))
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "status":
            refresh(root)
            print((memory / "STATUS.md").read_text(encoding="utf-8"))
        elif args.command == "flow":
            project = read_json(memory / "project.json")
            print(render_flow(project, load_nodes(root), args.phase))
        elif args.command == "handoff":
            refresh(root)
            print(str(memory / "HANDOFF.md"))
        elif args.command == "refresh":
            refresh(root)
            print("已重新生成 PROJECT.md、STATUS.md、FLOW.md、HANDOFF.md")
        return 0
    except (OSError, ValueError, TimeoutError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
