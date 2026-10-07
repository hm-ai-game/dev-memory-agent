import json
import re
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
        flow = (self.root / ".dev-memory" / "FLOW.md").read_text(encoding="utf-8")
        self.assertRegex(flow, r"n\d+ --> n\d+")
        self.assertIn("原因：首版只在 Codex 使用", flow)
        self.assertIn("方案 远端服务：可取之处 易同步；顾虑 首版部署成本高", flow)
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

    def test_decision_requires_a_specific_choice_and_reason(self):
        with self.assertRaisesRegex(ValueError, "decision 节点必须"):
            append_node(self.root, {"kind": "decision", "title": "方案选择", "summary": "已选择"})
        with self.assertRaisesRegex(ValueError, "chosen_option 必须匹配"):
            append_node(self.root, self.sample(chosen_option="第三种方案"))

    def test_new_requirement_updates_progress_and_flow_without_erasing_history(self):
        decision = append_node(self.root, self.sample())
        requirement = append_node(self.root, {
            "kind": "requirement",
            "title": "增加跨项目检索",
            "summary": "用户需要按项目隔离后仍能选择性检索多个项目",
            "phase": "需求扩展",
            "acceptance_criteria": ["查询结果标明所属项目"],
            "predecessors": [decision["id"]],
            "affects": [decision["id"]],
        })
        self.assertEqual(requirement["status"], "planned")
        status = (self.root / ".dev-memory" / "STATUS.md").read_text(encoding="utf-8")
        flow = (self.root / ".dev-memory" / "FLOW.md").read_text(encoding="utf-8")
        self.assertIn("待开发需求", status)
        self.assertIn("增加跨项目检索", status)
        self.assertIn("新需求影响", flow)
        self.assertIn("查询结果标明所属项目", flow)
        self.assertEqual(len(load_nodes(self.root)), 2)
        updated = append_node(self.root, {"status": "completed"}, revise_id=requirement["id"])
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(len((self.root / ".dev-memory" / "NODES.jsonl").read_text(encoding="utf-8").splitlines()), 3)

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

    def test_claude_turns_share_memory_and_require_a_decision_each_time(self):
        hook = [sys.executable, str(ROOT / "hooks" / "claude_memory.py")]
        session = "claude-session-123"

        def fire(name, **extra):
            event = {
                "cwd": str(self.root),
                "session_id": session,
                "hook_event_name": name,
                **extra,
            }
            return subprocess.check_output(hook, input=json.dumps(event).encode("utf-8"))

        self.assertIn(b"Development memory is enabled", fire("SessionStart"))
        prompt = json.loads(fire("UserPromptSubmit", prompt="private prompt text"))
        context = prompt["hookSpecificOutput"]["additionalContext"]
        first_turn = re.search(r"claude-[0-9a-f]{32}", context).group()
        self.assertEqual(json.loads(fire("Stop"))["decision"], "block")
        self.assertNotIn(
            "private prompt text",
            "".join(path.read_text(encoding="utf-8") for path in (self.root / ".dev-memory" / ".runtime").rglob("*.json")),
        )
        subprocess.check_call([
            sys.executable, str(ROOT / "memory.py"), "ack",
            "--project", str(self.root), "--turn-id", first_turn,
        ], stdout=subprocess.DEVNULL)
        self.assertEqual(json.loads(fire("Stop")), {})

        second = json.loads(fire("UserPromptSubmit", prompt="another private prompt"))
        second_turn = re.search(r"claude-[0-9a-f]{32}", second["hookSpecificOutput"]["additionalContext"]).group()
        self.assertNotEqual(first_turn, second_turn)
        self.assertEqual(json.loads(fire("Stop"))["decision"], "block")
        input_path = self.root / ".dev-memory" / "inbox" / "node.json"
        input_path.write_text(json.dumps(self.sample(), ensure_ascii=False), encoding="utf-8")
        subprocess.check_call([
            sys.executable, str(ROOT / "memory.py"), "record",
            "--project", str(self.root), "--input", str(input_path), "--turn-id", second_turn,
        ], stdout=subprocess.DEVNULL)
        self.assertEqual(json.loads(fire("Stop")), {})
        self.assertEqual(len(load_nodes(self.root)), 1)


if __name__ == "__main__":
    unittest.main()
