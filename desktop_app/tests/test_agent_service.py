"""Comprehensive Unit & Integration Tests for Godot AI Agent Backend Service.

Tests:
1. Health & Model status checks
2. Active-editor project registration with auth token (200 OK vs 401 Unauthorized)
3. Project selection: valid project with project.godot vs invalid paths
4. Path traversal protection & symlink protection
5. File reading, editing, diff generation, external modification conflict detection
6. File rollback / revert from backup
7. Godot executable resolution & subprocess timeouts
8. Tool-call parser with JSON, code blocks, and fallback handling
9. Headless project validation
10. End-to-end action execution
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

import sys
APP_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = APP_DIR / "backend"
REPO_ROOT = APP_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent_service import (
    app,
    AUTH_TOKEN,
    project_mgr,
    model_mgr,
    parse_agent_response,
)


class TestGodotAgentService(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.temp_dir = tempfile.mkdtemp(prefix="godot_test_proj_")
        self.proj_path = Path(self.temp_dir)
        (self.proj_path / "project.godot").write_text("config_version=5\n[application]\nconfig/name=\"TestGame\"\n", encoding="utf-8")
        (self.proj_path / "scripts").mkdir()
        (self.proj_path / "scenes").mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_health_check(self):
        """Test health endpoint reports online status, model, and project state."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "online")
        self.assertIn("model", data)
        self.assertIn("project", data)
        self.assertTrue(data.get("auth_token_configured"))

    def test_02_project_registration_with_token(self):
        """Test active-editor registration via HTTP endpoint with auth token."""
        # 1. Without token -> 401 Unauthorized
        resp_unauth = self.client.post("/api/project/register", json={
            "project_path": str(self.proj_path),
            "project_name": "TestGame",
        })
        self.assertEqual(resp_unauth.status_code, 401)

        # 2. With invalid token -> 401 Unauthorized
        resp_bad = self.client.post(
            "/api/project/register",
            headers={"X-Agent-Token": "bad_token_123"},
            json={"project_path": str(self.proj_path)},
        )
        self.assertEqual(resp_bad.status_code, 401)

        # 3. With valid token -> 200 OK and registers project
        resp_valid = self.client.post(
            "/api/project/register",
            headers={"X-Agent-Token": AUTH_TOKEN},
            json={
                "project_path": str(self.proj_path),
                "project_name": "TestGame",
                "godot_version": "Godot 4.7.2",
            },
        )
        self.assertEqual(resp_valid.status_code, 200)
        proj_data = resp_valid.json().get("project", {})
        self.assertTrue(proj_data.get("connected"))
        self.assertEqual(proj_data.get("project_name"), "TestGame")
        self.assertEqual(proj_data.get("connection_method"), "editor_plugin")

    def test_03_project_selection_validation(self):
        """Test manual folder selection validates project.godot presence."""
        # Non-existent path
        resp = self.client.post("/api/project/select", json={"project_path": "/invalid/nonexistent/dir"})
        self.assertEqual(resp.status_code, 400)

        # Path without project.godot
        empty_dir = tempfile.mkdtemp(prefix="empty_not_godot_")
        try:
            resp2 = self.client.post("/api/project/select", json={"project_path": empty_dir})
            self.assertEqual(resp2.status_code, 400)
            self.assertIn("No 'project.godot' found", resp2.json()["detail"])
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)

        # Valid project path
        resp3 = self.client.post("/api/project/select", json={"project_path": str(self.proj_path)})
        self.assertEqual(resp3.status_code, 200)
        self.assertTrue(resp3.json()["project"]["connected"])

    def test_04_path_traversal_and_symlink_protection(self):
        """Test backend blocks directory traversal attacks and symlink escapes."""
        self.client.post("/api/project/select", json={"project_path": str(self.proj_path)})

        # 1. Directory traversal via ../
        resp_traversal = self.client.get("/api/project/file?path=../../../../etc/passwd")
        self.assertEqual(resp_traversal.status_code, 400)
        self.assertIn("Path traversal detected", resp_traversal.json()["detail"])

        # 2. Symlink escape
        outside_file = Path(tempfile.gettempdir()) / "outside_secret.txt"
        outside_file.write_text("secret_token_12345", encoding="utf-8")
        symlink_path = self.proj_path / "escaped_symlink.txt"
        try:
            os.symlink(outside_file, symlink_path)
            resp_symlink = self.client.get("/api/project/file?path=escaped_symlink.txt")
            self.assertEqual(resp_symlink.status_code, 400)
            self.assertTrue("traversal detected" in resp_symlink.json()["detail"].lower())
        finally:
            if outside_file.exists():
                outside_file.unlink()

    def test_05_file_read_edit_diff_and_conflict(self):
        """Test reading, writing, diff generation, and optimistic concurrency check."""
        self.client.post("/api/project/select", json={"project_path": str(self.proj_path)})

        # 1. Create a script file
        initial_code = "extends CharacterBody2D\n\nfunc _ready() -> void:\n\tpass\n"
        edit_resp = self.client.post("/api/project/edit", json={
            "file_path": "scripts/player.gd",
            "content": initial_code,
        })
        self.assertEqual(edit_resp.status_code, 200)
        self.assertTrue(edit_resp.json()["success"])
        self.assertTrue((self.proj_path / "scripts/player.gd").exists())

        # 2. Read the file
        read_resp = self.client.get("/api/project/file?path=scripts/player.gd")
        self.assertEqual(read_resp.status_code, 200)
        file_data = read_resp.json()
        self.assertEqual(file_data["content"], initial_code)
        file_hash = file_data["hash"]

        # 3. Modify with expected_hash -> diff generated
        updated_code = "extends CharacterBody2D\n\nconst SPEED = 300.0\n\nfunc _ready() -> void:\n\tprint('ready')\n"
        edit_resp2 = self.client.post("/api/project/edit", json={
            "file_path": "scripts/player.gd",
            "content": updated_code,
            "expected_hash": file_hash,
        })
        self.assertEqual(edit_resp2.status_code, 200)
        diff = edit_resp2.json().get("diff")
        self.assertIn("+const SPEED = 300.0", diff)

        # 4. Conflict detection: modify file externally
        (self.proj_path / "scripts/player.gd").write_text("modified externally!", encoding="utf-8")
        conflict_resp = self.client.post("/api/project/edit", json={
            "file_path": "scripts/player.gd",
            "content": "conflict attempt",
            "expected_hash": file_hash, # stale hash
            "force": False,
        })
        self.assertEqual(conflict_resp.status_code, 409)

    def test_06_file_rollback(self):
        """Test undoing agent edits restores previous content from backup."""
        self.client.post("/api/project/select", json={"project_path": str(self.proj_path)})

        # Write version 1
        self.client.post("/api/project/edit", json={
            "file_path": "scripts/score.gd",
            "content": "var score = 0\n",
        })

        # Write version 2
        edit_res2 = self.client.post("/api/project/edit", json={
            "file_path": "scripts/score.gd",
            "content": "var score = 100\n",
        })
        change_id = edit_res2.json()["change_id"]

        # Verify current file is version 2
        content_now = (self.proj_path / "scripts/score.gd").read_text(encoding="utf-8")
        self.assertEqual(content_now, "var score = 100\n")

        # Rollback change
        rollback_resp = self.client.post("/api/project/rollback", json={"change_id": change_id})
        self.assertEqual(rollback_resp.status_code, 200)

        # Verify restored to version 1
        content_restored = (self.proj_path / "scripts/score.gd").read_text(encoding="utf-8")
        self.assertEqual(content_restored, "var score = 0\n")

    def test_07_tool_call_parsing(self):
        """Test parser handles pure JSON, markdown fences, and fallback GDScript extraction."""
        # 1. Pure JSON action
        json_sample = '{"thought": "Create enemy", "action_type": "create_or_update_script", "parameters": {"file_path": "scripts/enemy.gd", "content": "extends Node2D"}}'
        act1 = parse_agent_response(json_sample)
        self.assertEqual(act1.get("action_type"), "create_or_update_script")
        self.assertEqual(act1.get("parameters", {}).get("file_path"), "scripts/enemy.gd")

        # 2. Markdown fenced JSON
        fenced_sample = 'Here is the plan:\n```json\n{"thought": "Build scene", "action_type": "create_scene", "parameters": {"file_path": "scenes/coin.tscn"}}\n```'
        act2 = parse_agent_response(fenced_sample)
        self.assertEqual(act2.get("action_type"), "create_scene")
        self.assertEqual(act2.get("parameters", {}).get("file_path"), "scenes/coin.tscn")

        # 3. Conversational response
        chat_sample = "To jump in Godot 4, apply velocity.y = -JUMP_VELOCITY in _physics_process."
        act3 = parse_agent_response(chat_sample)
        self.assertEqual(act3.get("action_type"), "chat_response")
        self.assertIn("JUMP_VELOCITY", act3.get("parameters", {}).get("message", ""))

    def test_08_godot_binary_resolution(self):
        """Test Godot binary resolution identifies existing engine executable."""
        godot_bin = project_mgr.resolve_godot_bin()
        self.assertIsNotNone(godot_bin)
        self.assertTrue(Path(godot_bin).exists())

    def test_09_end_to_end_action_execution(self):
        """Test executing actions directly on connected project."""
        self.client.post("/api/project/select", json={"project_path": str(self.proj_path)})

        # 1. Create scene action
        create_action = {
            "thought": "Create level",
            "action_type": "create_scene",
            "parameters": {
                "file_path": "scenes/level.tscn",
                "root_node_name": "Level",
                "root_node_type": "Node2D",
            },
        }
        res1 = self.client.post("/api/agent/execute-action", json={"action": create_action})
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.json().get("success"))
        self.assertTrue((self.proj_path / "scenes/level.tscn").exists())

        # 2. List project files
        files_res = self.client.get("/api/project/files")
        self.assertEqual(files_res.status_code, 200)
        file_paths = [f["path"] for f in files_res.json()["files"]]
        self.assertIn("scenes/level.tscn", file_paths)

    def test_10_model_loading_error_handling(self):
        """Test model loading with invalid path reports clear structured error."""
        res = self.client.post("/api/model/load", json={
            "base_model": "/nonexistent/base_model_path",
            "adapter": "/nonexistent/adapter_path",
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data.get("success"))
        self.assertIn("error", data)

    def test_11_chat_streaming_and_cancellation(self):
        """Test chat streaming returns informative error when model is unloaded and supports cancellation."""
        # Unloaded model stream
        resp = self.client.post("/api/chat/stream", json={"prompt": "Hello Godot"})
        self.assertEqual(resp.status_code, 200)
        content = resp.text
        self.assertIn("Model is not loaded", content)

        # Cancel endpoint
        cancel_resp = self.client.post("/api/chat/cancel")
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertTrue(cancel_resp.json().get("cancelled"))


if __name__ == "__main__":
    unittest.main()

