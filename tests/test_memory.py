import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from memory import append_node, find_project, initialize, load_nodes, mark_turn, query_nodes


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project-a"
        self.root.mkdir()
        initialize(self.root, "测试项目", "做出可靠的开发记忆", "只记录开发节点")

    def tearDown(self):
        self.temp.cleanup()

    def sample(self, **extra):
        return {
            "kind": "decision",
            "title": "选择本地存储",
            "summary": "项目记忆保存在本地",
            "phase": "核心记忆",
            "options": [
                {"name": "本地文件", "reason_for": "易交接", "reason_against": "并发受限"},
                {"name": "远端服务", "reason_for": "易同步", "reason_against": "首版部署成本高"},
            ],
            "chosen_option": "本地文件",
            "rationale": "首版只在 Codex 使用",
            "evidence_level": "reported",
            **extra,
        }

    def test_record_query_and_derived_handoff(self):
        first = append_node(self.root, self.sample(source_key="turn1-choice"))
        second = append_node(self.root, {
            "kind": "verification",
            "title": "验证节点生成",
            "summary": "测试通过",
            "phase": "核心记忆",
            "status": "completed",
            "evidence_level": "tested",
            "evidence": [{"type": "test", "ref": "python -m unittest", "result": "exit code 0"}],
            "predecessors": [first["id"]],
        })
        self.assertEqual(len(load_nodes(self.root)), 2)
        self.assertEqual(query_nodes(load_nodes(self.root), "本地存储", None, None, 10)[0]["id"], first["id"])
        self.assertIn("n0 --> n1", (self.root / ".dev-memory" / "FLOW.md").read_text(encoding="utf-8"))
        self.assertIn("测试通过", json.dumps(second, ensure_ascii=False))
        self.assertIn("交接入口", (self.root / ".dev-memory" / "HANDOFF.md").read_text(encoding="utf-8"))

    def test_retries_are_idempotent_and_revisions_preserve_history(self):
        first = append_node(self.root, self.sample(source_key="turn1-choice"))
        repeat = append_node(self.root, self.sample(source_key="turn1-choice"))
        self.assertEqual(first["id"], repeat["id"])
        self.assertEqual(len((self.root / ".dev-memory" / "NODES.jsonl").read_text(encoding="utf-8").splitlines()), 1)
        updated = append_node(self.root, {"outcome": "已实现"}, revise_id=first["id"])
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(len((self.root / ".dev-memory" / "NODES.jsonl").read_text(encoding="utf-8").splitlines()), 2)
        self.assertEqual(load_nodes(self.root)[first["id"]]["outcome"], "已实现")

    def test_major_change_requires_approval_before_project_update(self):
        proposed = append_node(self.root, {
            "kind": "direction_change",
            "title": "扩大项目范围",
            "summary": "提议扩展到另一个平台",
            "phase": "规划",
            "project_update": {"scope": "支持更多平台"},
        })
        self.assertEqual(proposed["status"], "pending_approval")
        project_file = self.root / ".dev-memory" / "project.json"
        self.assertEqual(json.loads(project_file.read_text(encoding="utf-8"))["scope"], "只记录开发节点")
        approved = append_node(self.root, {"approved_by_user": True}, revise_id=proposed["id"])
        self.assertEqual(approved["status"], "completed")
        self.assertEqual(json.loads(project_file.read_text(encoding="utf-8"))["scope"], "支持更多平台")

    def test_raw_conversation_fields_rejected_and_projects_isolated(self):
        with self.assertRaisesRegex(ValueError, "对话原文"):
            append_node(self.root, self.sample(transcript="raw chat"))
        other = Path(self.temp.name) / "project-b"
        other.mkdir()
        initialize(other, "项目 B", "另一个目标", "")
        append_node(self.root, self.sample())
        self.assertEqual(len(load_nodes(other)), 0)
        self.assertEqual(find_project(other / "nested"), other.resolve())

    def test_stop_hook_requests_record_or_ack_once(self):
        turn = "turn-123"
        command = [sys.executable, str(ROOT / "hooks" / "auto_memory.py")]
        event = {"cwd": str(self.root), "hook_event_name": "Stop", "turn_id": turn, "stop_hook_active": False}
        output = subprocess.check_output(command, input=json.dumps(event).encode("utf-8"))
        self.assertEqual(json.loads(output)["decision"], "block")
        mark_turn(self.root, turn, "no_node")
        output = subprocess.check_output(command, input=json.dumps(event).encode("utf-8"))
        self.assertEqual(json.loads(output), {})

    def test_inactive_project_gets_no_session_context(self):
        other = Path(self.temp.name) / "untracked"
        other.mkdir()
        command = [sys.executable, str(ROOT / "hooks" / "auto_memory.py")]
        event = {"cwd": str(other), "hook_event_name": "SessionStart"}
        output = subprocess.check_output(command, input=json.dumps(event).encode("utf-8"))
        self.assertEqual(output, b"")


if __name__ == "__main__":
    unittest.main()
