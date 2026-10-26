"""Regression Tests for CLI Plan Lifecycle, Project Metadata, and Inspection Planning."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from logic.orchestrator.executor import TaskExecutionResult, TaskExecutor
from logic.orchestrator.models import ProjectPlan, TaskItem, TaskStatus
from logic.orchestrator.orchestrator import AutonomousProjectOrchestrator
from logic.orchestrator.planner import IntelligentTaskPlanner
from logic.orchestrator.project_analyzer import GodotProjectAnalyzer

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestCliAndLifecycleRegression(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name)

        # Create a realistic Godot 4 project structure
        proj_godot_content = (
            "config_version=5\n"
            "[application]\n"
            "config/name=\"SmokeGame\"\n"
            "config/features=PackedStringArray(\"4.2\")\n"
            "run/main_scene=\"res://main.tscn\"\n"
            "[autoload]\n"
            "GlobalState=\"*res://scripts/global_state.gd\"\n"
        )
        (self.project_path / "project.godot").write_text(proj_godot_content, encoding="utf-8")
        (self.project_path / "scripts").mkdir()
        (self.project_path / "player").mkdir()
        (self.project_path / "scenes").mkdir()

        # Scripts
        self.global_state = self.project_path / "scripts" / "global_state.gd"
        self.global_state.write_text("extends Node\nvar coins: int = 0\n", encoding="utf-8")

        self.player_script = self.project_path / "player" / "player.gd"
        self.player_script.write_text(
            "class_name Player extends CharacterBody2D\n\n"
            "const WALK_SPEED = 300.0\n"
            "const TERMINAL_VELOCITY = 700\n\n"
            "func _physics_process(delta: float) -> void:\n"
            "\tif Input.is_action_just_released(\"jump\") and velocity.y < 0.0:\n"
            "\t\tvelocity.y *= 0.6\n"
            "\tmove_and_slide()\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_metadata_extraction_identifies_version_and_features(self) -> None:
        """Verifies engine_version and features are extracted from config/features."""
        analyzer = GodotProjectAnalyzer(self.project_path)
        meta = analyzer.get_project_metadata()

        self.assertTrue(meta["valid"])
        self.assertEqual(meta["engine_version"], "4.2")
        self.assertEqual(meta["features"], ["4.2"])
        self.assertIn("GlobalState", meta["autoloads"])
        self.assertEqual(meta["config_version"], 5)

    def test_plan_only_then_execute_persisted_plan(self) -> None:
        """Verifies that a plan created with --plan-only can be executed by --execute without re-planning."""
        plan_calls = 0
        exec_calls = 0

        def mock_generator(msgs: list) -> str:
            nonlocal plan_calls, exec_calls
            sys_msg = msgs[0]["content"]
            if "planner" in sys_msg.lower():
                plan_calls += 1
                return json.dumps({
                    "is_complex": True,
                    "summary": "Plan safe jump cut multiplier",
                    "tasks": [
                        {
                            "id": "task_01_safe_improvement",
                            "description": "Expose jump_cut_multiplier in player/player.gd",
                            "target_files": ["player/player.gd"],
                            "dependencies": [],
                            "acceptance_criteria": ["Godot 4 compiler validation passes"],
                        }
                    ],
                })
            else:
                exec_calls += 1
                return json.dumps({
                    "thought": "Expose jump_cut_multiplier",
                    "action_type": "create_or_update_script",
                    "parameters": {
                        "file_path": "player/player.gd",
                        "content": (
                            "class_name Player extends CharacterBody2D\n\n"
                            "@export var jump_cut_multiplier: float = 0.6\n"
                            "const WALK_SPEED = 300.0\n"
                            "const TERMINAL_VELOCITY = 700\n\n"
                            "func _physics_process(delta: float) -> void:\n"
                            "\tif Input.is_action_just_released(\"jump\") and velocity.y < 0.0:\n"
                            "\t\tvelocity.y *= jump_cut_multiplier\n"
                            "\tmove_and_slide()\n"
                        ),
                    },
                })

        orchestrator = AutonomousProjectOrchestrator(self.project_path, generator_fn=mock_generator)

        # Step 1: Generate plan only (simulating --plan-only)
        plan = orchestrator.plan("Inspect the existing project, identify one safe improvement, implement it, and validate the result. Preserve unrelated functionality.")
        self.assertIsNotNone(plan)
        self.assertTrue(orchestrator.plan_file.exists())
        self.assertEqual(plan.status, "planning")
        self.assertEqual(exec_calls, 0)  # No execution yet

        # Step 2: Execute existing persisted plan (simulating --execute without --request)
        loaded_plan = orchestrator.get_current_plan()
        self.assertIsNotNone(loaded_plan)
        summary = orchestrator.execute_plan(loaded_plan)

        self.assertEqual(summary["overall_status"], "completed")
        self.assertEqual(summary["passed_count"], len(loaded_plan.tasks))
        self.assertIn("player/player.gd", summary["modified_files"])
        self.assertIn("@export var jump_cut_multiplier: float = 0.6", self.player_script.read_text(encoding="utf-8"))

    def test_execute_without_plan_raises_actionable_error(self) -> None:
        """Verifies that attempting to execute without an existing plan produces a clear ValueError."""
        empty_temp = tempfile.TemporaryDirectory()
        empty_proj = Path(empty_temp.name)
        (empty_proj / "project.godot").write_text("config_version=5\n", encoding="utf-8")

        orchestrator = AutonomousProjectOrchestrator(empty_proj)
        with self.assertRaises(ValueError) as ctx:
            orchestrator.execute_plan(plan=None)
        self.assertIn("No plan provided and no existing plan found on disk", str(ctx.exception))
        empty_temp.cleanup()

    def test_open_ended_inspection_selects_real_script_and_justified_improvement(self) -> None:
        """Verifies that an open-ended request inspects project scripts and produces concrete tasks."""
        planner = IntelligentTaskPlanner(self.project_path)
        plan = planner.plan_request(
            "Inspect the existing project, identify one safe improvement, implement it, and validate the result. Preserve unrelated functionality."
        )

        self.assertTrue(plan.is_complex)
        self.assertGreaterEqual(len(plan.tasks), 1)

        task1 = plan.tasks[0]
        # Target file must be a real project file!
        self.assertIn("player/player.gd", task1.target_files)
        # Description must explain the concrete improvement
        self.assertIn("player/player.gd", task1.description)
        self.assertTrue(
            "Jump Cut Multiplier" in task1.description or "Speed Scale" in task1.description or "Validation" in task1.description
        )
        self.assertFalse("Implement core functionality for: Inspect" in task1.description)

    def test_staging_copies_project_environment_so_dependencies_resolve(self) -> None:
        """Verifies staging sandbox contains project dependencies (autoloads, custom classes)."""
        executor = TaskExecutor(self.project_path)
        with tempfile.TemporaryDirectory() as stage:
            stage_dir = Path(stage)
            executor._prepare_staging_environment(stage_dir)

            # Staging directory must contain cloned project files
            self.assertTrue((stage_dir / "project.godot").exists())
            self.assertTrue((stage_dir / "scripts" / "global_state.gd").exists())
            self.assertTrue((stage_dir / "player" / "player.gd").exists())


    def test_parameter_modification_plan_and_execute_lifecycle(self) -> None:
        """Verifies single-file parameter modification plans as focused task and executes cleanly."""
        orchestrator = AutonomousProjectOrchestrator(self.project_path)
        plan = orchestrator.plan(
            "Increase WALK_SPEED to 350.0 in player/player.gd. Preserve all other movement behavior and validate the change."
        )
        self.assertFalse(plan.is_complex)
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(plan.tasks[0].target_files, ["player/player.gd"])
        self.assertTrue(orchestrator.plan_file.exists())

        # Execute existing persisted plan
        summary = orchestrator.execute_plan()
        self.assertEqual(summary["overall_status"], "completed")
        self.assertEqual(summary["passed_count"], 1)
        self.assertIn("player/player.gd", summary["modified_files"])
        self.assertIn("const WALK_SPEED = 350.0", self.player_script.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
