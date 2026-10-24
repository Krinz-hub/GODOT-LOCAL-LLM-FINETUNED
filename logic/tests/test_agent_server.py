"""Tests for the Godot Local AI Agent Server and Action Execution."""

from http import HTTPStatus
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error

import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from godot_agent_server import (
    GodotAgentHTTPHandler,
    ThreadingHTTPServer,
    execute_action,
    extract_json_from_text,
)

TEST_PORT = 8999


class TestGodotAgentServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", TEST_PORT), GodotAgentHTTPHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_health_endpoint(self):
        req = urllib.request.Request(f"http://127.0.0.1:{TEST_PORT}/health")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, HTTPStatus.OK)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "online")
            self.assertIn("service", data)

    def test_schema_endpoint(self):
        req = urllib.request.Request(f"http://127.0.0.1:{TEST_PORT}/schema")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, HTTPStatus.OK)
            schema = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(schema.get("title"), "GodotAgentAction")
            self.assertIn("action_type", schema.get("properties", {}))

    def test_json_extractor_handles_fences(self):
        text = """Here is the action:
```json
{
  "thought": "Create enemy script",
  "action_type": "create_or_update_script",
  "parameters": {
    "file_path": "scripts/enemy.gd",
    "content": "extends CharacterBody2D\\n"
  }
}
```
Done!"""
        action = extract_json_from_text(text)
        self.assertEqual(action.get("action_type"), "create_or_update_script")
        self.assertEqual(action.get("parameters", {}).get("file_path"), "scripts/enemy.gd")

    def test_execute_create_script_in_project(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "project.godot").write_text("config_version=5\n", encoding="utf-8")

            action = {
                "thought": "Create player",
                "action_type": "create_or_update_script",
                "parameters": {
                    "file_path": "player.gd",
                    "content": "extends CharacterBody2D\n\nfunc _ready() -> void:\n\tpass\n",
                },
            }

            res = execute_action(str(tmp_path), action)
            self.assertTrue(res.get("success"))
            self.assertTrue((tmp_path / "player.gd").exists())

            # Read back file
            read_action = {
                "thought": "Read back player",
                "action_type": "read_file",
                "parameters": {"file_path": "player.gd"},
            }
            read_res = execute_action(str(tmp_path), read_action)
            self.assertTrue(read_res.get("success"))
            self.assertIn("extends CharacterBody2D", read_res.get("content", ""))

    def test_execute_prevents_directory_traversal(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            action = {
                "thought": "Malicious write",
                "action_type": "create_or_update_script",
                "parameters": {
                    "file_path": "../malicious.gd",
                    "content": "exploit",
                },
            }
            with self.assertRaises(ValueError):
                execute_action(tmp_dir, action)

    def test_chat_session_persistence(self):
        from godot_agent_server import SESSIONS
        url = f"http://127.0.0.1:{TEST_PORT}/v1/chat"

        # Turn 1
        data1 = json.dumps({"prompt": "Hello Godot", "session_id": "test_sess_1"}).encode("utf-8")
        req1 = urllib.request.Request(url, data=data1, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req1) as resp:
            self.assertEqual(resp.status, HTTPStatus.OK)
            res1 = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res1.get("session_id"), "test_sess_1")

        self.assertIn("test_sess_1", SESSIONS)
        self.assertEqual(len(SESSIONS["test_sess_1"]), 3)  # system, user, assistant

        # Turn 2
        data2 = json.dumps({"prompt": "Follow up question", "session_id": "test_sess_1"}).encode("utf-8")
        req2 = urllib.request.Request(url, data=data2, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req2) as resp:
            self.assertEqual(resp.status, HTTPStatus.OK)
            res2 = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res2.get("session_id"), "test_sess_1")

        # Verify session accumulated turns
        self.assertEqual(len(SESSIONS["test_sess_1"]), 5)  # system, user1, asst1, user2, asst2
        self.assertEqual(SESSIONS["test_sess_1"][1]["content"], "Hello Godot")
        self.assertEqual(SESSIONS["test_sess_1"][3]["content"], "Follow up question")

    def test_godot_binary_discovery(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "project.godot").write_text("config_version=5\n[application]\nconfig/name=\"Test\"\n", encoding="utf-8")
            action = {
                "action_type": "run_project",
                "parameters": {"command": "--version"},
            }
            res = execute_action(str(tmp_path), action)
            # Must find the executable and execute successfully
            self.assertTrue(res.get("success"), f"Execution failed: {res}")
            self.assertIn("4.", res.get("stdout", ""))

    def test_scene_endpoints_create_edit_delete(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Test POST /v1/scene/create
            create_payload = json.dumps({
                "project_path": tmp_dir,
                "file_path": "scenes/main.tscn",
                "root_node_name": "Main",
                "root_node_type": "Node2D",
                "script_path": "res://scripts/main.gd",
            }).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{TEST_PORT}/v1/scene/create",
                data=create_payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, HTTPStatus.OK)
                res = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(res.get("success"))
                self.assertEqual(res.get("file_path"), "scenes/main.tscn")

            scene_file = Path(tmp_dir) / "scenes" / "main.tscn"
            self.assertTrue(scene_file.exists())
            content = scene_file.read_text(encoding="utf-8")
            self.assertIn('[node name="Main" type="Node2D"]', content)
            self.assertIn('[ext_resource type="Script" path="res://scripts/main.gd"', content)

            # 2. Test GET /v1/scene
            get_url = f"http://127.0.0.1:{TEST_PORT}/v1/scene?project_path={urllib.parse.quote(tmp_dir)}&file_path=scenes/main.tscn"
            with urllib.request.urlopen(get_url) as resp:
                self.assertEqual(resp.status, HTTPStatus.OK)
                read_res = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(read_res.get("success"))
                self.assertIn("Main", read_res.get("content", ""))

            # 3. Test POST /v1/scene/edit with add_nodes
            edit_payload = json.dumps({
                "project_path": tmp_dir,
                "file_path": "scenes/main.tscn",
                "add_nodes": [
                    {"name": "Player", "type": "CharacterBody2D", "parent": "."}
                ],
            }).encode("utf-8")
            req_edit = urllib.request.Request(
                f"http://127.0.0.1:{TEST_PORT}/v1/scene/edit",
                data=edit_payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req_edit) as resp:
                self.assertEqual(resp.status, HTTPStatus.OK)
                edit_res = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(edit_res.get("success"))

            updated_content = scene_file.read_text(encoding="utf-8")
            self.assertIn('[node name="Player" type="CharacterBody2D" parent="."]', updated_content)

            # 4. Test POST /v1/scene/delete
            del_payload = json.dumps({
                "project_path": tmp_dir,
                "file_path": "scenes/main.tscn",
            }).encode("utf-8")
            req_del = urllib.request.Request(
                f"http://127.0.0.1:{TEST_PORT}/v1/scene/delete",
                data=del_payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req_del) as resp:
                self.assertEqual(resp.status, HTTPStatus.OK)
                del_res = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(del_res.get("success"))

            self.assertFalse(scene_file.exists())

    def test_execute_action_scene_actions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Action: create_scene
            act_create = {
                "action_type": "create_scene",
                "parameters": {
                    "file_path": "battle.tscn",
                    "root_node_name": "BattleArena",
                    "root_node_type": "Node2D",
                },
            }
            res_create = execute_action(tmp_dir, act_create)
            self.assertTrue(res_create.get("success"))
            self.assertTrue((Path(tmp_dir) / "battle.tscn").exists())

            # 2. Action: edit_scene
            act_edit = {
                "action_type": "edit_scene",
                "parameters": {
                    "file_path": "battle.tscn",
                    "content": "[gd_scene format=3]\n\n[node name=\"BattleArenaV2\" type=\"Node2D\"]\n",
                },
            }
            res_edit = execute_action(tmp_dir, act_edit)
            self.assertTrue(res_edit.get("success"))
            self.assertIn("BattleArenaV2", (Path(tmp_dir) / "battle.tscn").read_text(encoding="utf-8"))

            # 3. Action: delete_scene
            act_del = {
                "action_type": "delete_scene",
                "parameters": {"file_path": "battle.tscn"},
            }
            res_del = execute_action(tmp_dir, act_del)
            self.assertTrue(res_del.get("success"))
            self.assertFalse((Path(tmp_dir) / "battle.tscn").exists())

    def test_delete_scene_safety_restrictions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            script_file = tmp_path / "important.gd"
            script_file.write_text("extends Node\n", encoding="utf-8")

            # Must refuse to delete non-scene file (.gd)
            del_action = {
                "action_type": "delete_scene",
                "parameters": {"file_path": "important.gd"},
            }
            res = execute_action(tmp_dir, del_action)
            self.assertFalse(res.get("success"))
            self.assertIn("Refusing to delete non-scene file", res.get("error", ""))
            self.assertTrue(script_file.exists())

            # Must prevent path traversal attack
            traversal_action = {
                "action_type": "delete_scene",
                "parameters": {"file_path": "../outside.tscn"},
            }
            with self.assertRaises(ValueError):
                execute_action(tmp_dir, traversal_action)


if __name__ == "__main__":
    unittest.main()


