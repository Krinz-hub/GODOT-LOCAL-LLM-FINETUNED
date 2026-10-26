"""End-to-End Acceptance Tests (Test A & Test B) on Real Project Replicas."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from logic.orchestrator.executor import GODOT_BIN, TaskExecutionResult, TaskExecutor
from logic.orchestrator.models import ProjectPlan, TaskItem, TaskStatus
from logic.orchestrator.orchestrator import AutonomousProjectOrchestrator
from logic.orchestrator.planner import IntelligentTaskPlanner
from logic.orchestrator.project_analyzer import GodotProjectAnalyzer

REPO_ROOT = Path(__file__).resolve().parents[2]
PLATFORMER_PROJECT = REPO_ROOT / "2d_platformer" / "platformer"


class TestAcceptanceWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_project = Path(self.temp_dir.name) / "test_game"
        # Clone real 2D platformer demo project into isolated sandbox
        shutil.copytree(PLATFORMER_PROJECT, self.test_project)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_acceptance_test_a_simple_safe_improvement(self) -> None:
        """Test A: Prompt: 'Inspect the existing project and make one small, safe, clearly justified improvement.

        Preserve unrelated functionality and validate the project.'
        """
        request = (
            "Inspect the existing project and make one small, safe, clearly justified improvement. "
            "Preserve unrelated functionality and validate the project."
        )

        orchestrator = AutonomousProjectOrchestrator(self.test_project)

        # 1. Plan generation
        plan = orchestrator.plan(request)
        self.assertIsNotNone(plan)
        self.assertTrue(plan.is_complex)
        self.assertGreaterEqual(len(plan.tasks), 1)

        # 2. Verify inspection identifies concrete improvement
        task1 = plan.tasks[0]
        self.assertIn("player/player.gd", task1.target_files)
        self.assertIn("player/player.gd", task1.description)
        self.assertFalse("Implement core functionality for: Inspect" in task1.description)

        # 3. Execution with staging and engine validation
        summary = orchestrator.execute_plan(plan)
        self.assertEqual(summary["overall_status"], "completed")
        self.assertEqual(summary["passed_count"], len(plan.tasks))
        self.assertIn("player/player.gd", summary["modified_files"])

        # 4. Verify file was modified cleanly and preserves functionality
        player_code = (self.test_project / "player" / "player.gd").read_text(encoding="utf-8")
        self.assertIn("@export var jump_cut_multiplier: float = 0.6", player_code)
        self.assertIn("velocity.y *= jump_cut_multiplier", player_code)
        self.assertIn("const WALK_SPEED = 300.0", player_code)

    def test_acceptance_test_b_complex_multistep_pause_system(self) -> None:
        """Test B: Prompt: 'Add a pause system with pause menu, resume action, restart action, and keyboard shortcut'."""
        request = "Add a pause system with pause menu, resume action, restart action, and keyboard shortcut"

        orchestrator = AutonomousProjectOrchestrator(self.test_project)

        # 1. Plan generation produces multi-task DAG
        plan = orchestrator.plan(request)
        self.assertIsNotNone(plan)
        self.assertTrue(plan.is_complex)
        self.assertGreaterEqual(len(plan.tasks), 3)

        # Verify task ordering: scene -> script -> integration
        task_ids = [t.id for t in plan.tasks]
        self.assertIn("task_01_pause_menu_scene", task_ids)
        self.assertIn("task_02_pause_script", task_ids)
        self.assertIn("task_03_pause_integration", task_ids)

        # 2. Autonomous execution
        summary = orchestrator.execute_plan(plan)
        self.assertEqual(summary["overall_status"], "completed")
        self.assertEqual(summary["passed_count"], 3)
        self.assertEqual(summary["failed_count"], 0)
        self.assertEqual(summary["blocked_count"], 0)

        # 3. Verify created files exist and are valid
        pause_tscn = self.test_project / "gui" / "pause_menu.tscn"
        pause_gd = self.test_project / "gui" / "pause_menu.gd"
        self.assertTrue(pause_tscn.exists())
        self.assertTrue(pause_gd.exists())

        gd_code = pause_gd.read_text(encoding="utf-8")
        self.assertIn("class_name PauseMenuController extends Control", gd_code)
        self.assertIn("func toggle_pause()", gd_code)
        self.assertIn("func resume()", gd_code)
        self.assertIn("func restart()", gd_code)


if __name__ == "__main__":
    unittest.main()
