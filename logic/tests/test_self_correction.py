#!/usr/bin/env python3
"""Unit and Integration Tests for Bounded Self-Correction Execution Loop."""

from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.self_correction_loop import (
    parse_action_with_delimiters,
    run_bounded_self_correction,
    sanitize_relative_path,
)


class TestSelfCorrectionLoop(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_self_correction_")
        self.project_dir = Path(self.temp_dir)
        (self.project_dir / "project.godot").write_text("config_version=5\n[application]\nconfig/name=\"Test\"\n")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sanitize_relative_path_safety(self):
        # Valid relative paths
        p1 = sanitize_relative_path(self.project_dir, "scripts/player.gd")
        self.assertTrue(str(p1).startswith(str(self.project_dir)))

        # Directory traversal attacks must be blocked
        with self.assertRaises(PermissionError):
            sanitize_relative_path(self.project_dir, "../outside.gd")

        with self.assertRaises(PermissionError):
            sanitize_relative_path(self.project_dir, "../../etc/passwd")

    def test_parse_delimited_action_with_code_block(self):
        raw_text = """Plan: Create a clean CharacterBody2D script.
<godot_action>
{
  "thought": "Create enemy controller",
  "action_type": "create_or_update_script",
  "parameters": {
    "file_path": "enemy.gd"
  }
}
</godot_action>

```gdscript
extends CharacterBody2D

@export var speed: float = 150.0

func _physics_process(delta: float) -> void:
    move_and_slide()
```
"""
        action = parse_action_with_delimiters(raw_text)
        self.assertEqual(action.get("action_type"), "create_or_update_script")
        params = action.get("parameters", {})
        self.assertEqual(params.get("file_path"), "enemy.gd")
        content = params.get("content", "")
        self.assertIn("extends CharacterBody2D", content)
        self.assertIn("move_and_slide()", content)

    def test_self_correction_recovers_from_syntax_error(self):
        call_count = 0

        def mock_generator(conversation):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Attempt 1: Broken Godot 3 syntax
                return """```json
{
  "thought": "Create player",
  "action_type": "create_or_update_script",
  "parameters": {
    "file_path": "player.gd",
    "content": "extends CharacterBody2D\\n\\nfunc _physics_process(d):\\n    move_and_slide(velocity)\\n"
  }
}
```"""
            else:
                # Attempt 2: Corrected Godot 4 syntax
                return """```json
{
  "thought": "Fixed Godot 4 syntax",
  "action_type": "create_or_update_script",
  "parameters": {
    "file_path": "player.gd",
    "content": "extends CharacterBody2D\\n\\nfunc _physics_process(d: float) -> void:\\n    move_and_slide()\\n"
  }
}
```"""

        res = run_bounded_self_correction(
            project_path=self.project_dir,
            prompt="Create a player controller in player.gd",
            generator_fn=mock_generator,
            max_repair_attempts=2,
        )

        self.assertTrue(res.success, f"Expected self-correction to succeed. Diagnostics: {res.diagnostics}")
        self.assertEqual(res.total_attempts, 2)
        self.assertTrue((self.project_dir / "player.gd").exists())
        written_code = (self.project_dir / "player.gd").read_text()
        self.assertIn("move_and_slide()", written_code)

    def test_self_correction_bounds_attempts_and_preserves_project(self):
        call_count = 0

        def persistent_failing_generator(conversation):
            nonlocal call_count
            call_count += 1
            # Continues producing broken Godot 3 syntax with setget
            return """```json
{
  "thought": "Broken code",
  "action_type": "create_or_update_script",
  "parameters": {
    "file_path": "bad_script.gd",
    "content": "extends Node\\nvar x = 10 setget set_x\\n"
  }
}
```"""

        res = run_bounded_self_correction(
            project_path=self.project_dir,
            prompt="Create broken script",
            generator_fn=persistent_failing_generator,
            max_repair_attempts=2,
        )

        self.assertFalse(res.success)
        self.assertEqual(res.total_attempts, 3)  # Initial + 2 repairs = 3
        # Ensure bad file was NOT written to project
        self.assertFalse((self.project_dir / "bad_script.gd").exists(), "Bad script must not be committed to project")


if __name__ == "__main__":
    unittest.main()
