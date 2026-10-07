#!/usr/bin/env python3
"""Codex lifecycle hook: require a development-memory decision per turn."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from memory import MEMORY_DIR, find_project  # noqa: E402


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        print("{}")
        return
    root = find_project(Path(event.get("cwd") or Path.cwd()))
    name = event.get("hook_event_name")
    if root is None:
        if name != "SessionStart":
            print("{}")
        return
    turn_id = event.get("turn_id")
    command = f'python "{PLUGIN_ROOT / "memory.py"}"'
    if name == "SessionStart":
        status = root / MEMORY_DIR / "STATUS.md"
        summary = status.read_text(encoding="utf-8")[:2500] if status.exists() else ""
        print(
            f"Development memory is enabled for {root}. Read .dev-memory/PROJECT.md "
            "before making a project-direction decision. Current project status:\n" + summary
        )
    elif name == "UserPromptSubmit" and isinstance(turn_id, str):
        instruction = (
            "Development memory is enabled. At the end of this turn, if you implemented, "
            "verified, rejected, chose a development approach, or received a new requirement, record one or more concise "
            f"nodes with {command} record --project \"{root}\" --input <json-file> "
            f"--turn-id {turn_id}. If no durable development node occurred, run "
            f"{command} ack --project \"{root}\" --turn-id {turn_id}. "
            "Never store conversation text. Major direction or architecture changes need user approval."
        )
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": instruction,
            }
        }))
    elif name == "Stop" and isinstance(turn_id, str):
        marker = root / MEMORY_DIR / ".runtime" / "turns" / (turn_id + ".json")
        if marker.exists() or event.get("stop_hook_active"):
            print("{}")
        else:
            reason = (
                "Before finishing, review this turn for durable development nodes. "
                "If a new requirement, choice, implementation, test result, failed approach, blocker, or milestone occurred, "
                f"record it with {command} record --project \"{root}\" "
                f"--input <json-file> --turn-id {turn_id}. "
                "If none occurred, explicitly run "
                f"{command} ack --project \"{root}\" --turn-id {turn_id}. "
                "Do not persist conversation text. Then finish the user response."
            )
            print(json.dumps({"decision": "block", "reason": reason}))
    else:
        print("{}")


if __name__ == "__main__":
    main()
