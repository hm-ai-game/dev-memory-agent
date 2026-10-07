#!/usr/bin/env python3
"""Claude Code lifecycle hook for project-local development memory."""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from memory import MEMORY_DIR, find_project, read_json, write_json_atomic  # noqa: E402


def _current_turn_path(root: Path, session_id: str) -> Path:
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return root / MEMORY_DIR / ".runtime" / "claude-turns" / (session_key + ".json")


def _command(root: Path, turn_id: str, action: str) -> str:
    return (
        f'"{sys.executable}" "{PLUGIN_ROOT / "memory.py"}" {action} '
        f'--project "{root}" --turn-id {turn_id}'
    )


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        print("{}")
        return
    if not isinstance(event, dict):
        print("{}")
        return
    root = find_project(Path(event.get("cwd") or Path.cwd()))
    if root is None:
        print("{}")
        return
    name = event.get("hook_event_name")
    if name == "SessionStart":
        status = root / MEMORY_DIR / "STATUS.md"
        summary = status.read_text(encoding="utf-8")[:2500] if status.exists() else ""
        print(
            f"Development memory is enabled for {root}. Read .dev-memory/PROJECT.md "
            "before making a project-direction decision. Current project status:\n" + summary
        )
        return
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        print("{}")
        return
    current = _current_turn_path(root, session_id)
    if name == "UserPromptSubmit":
        turn_id = "claude-" + uuid.uuid4().hex
        write_json_atomic(current, {"turn_id": turn_id})
        instruction = (
            "Development memory is enabled. At the end of this turn, if you implemented, "
            "verified, rejected, chose a development approach, or received a new requirement, "
            "record concise nodes. Never store conversation text. "
            f"Use {_command(root, turn_id, 'record')} --input <json-file>. "
            "If no durable node occurred, run "
            f"{_command(root, turn_id, 'ack')}. "
            "Major direction or architecture changes need actual user approval."
        )
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": instruction,
            }
        }))
    elif name == "Stop":
        if event.get("stop_hook_active") or not current.exists():
            print("{}")
            return
        turn_id = read_json(current).get("turn_id")
        if not isinstance(turn_id, str):
            print("{}")
            return
        marker = root / MEMORY_DIR / ".runtime" / "turns" / (turn_id + ".json")
        if marker.exists():
            print("{}")
            return
        reason = (
            "Before finishing, review this turn for durable development nodes. "
            f"Record them with {_command(root, turn_id, 'record')} "
            "--input <json-file>, or explicitly run "
            f"{_command(root, turn_id, 'ack')} if there are none. "
            "Do not persist conversation text. Then finish the user response."
        )
        print(json.dumps({"decision": "block", "reason": reason}))
    else:
        print("{}")


if __name__ == "__main__":
    main()
