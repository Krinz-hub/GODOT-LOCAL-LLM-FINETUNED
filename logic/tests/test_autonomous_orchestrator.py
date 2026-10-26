"""Unit and Integration Tests for Autonomous Godot AI Orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from logic.orchestrator.executor import (
    TaskExecutionResult,
    TaskExecutor,
    parse_action_payload,
    sanitize_project_relative_path,
)
from logic.orchestrator.models import ProjectPlan, TaskItem, TaskStatus
from logic.orchestrator.orchestrator import AutonomousProjectOrchestrator
from logic.orchestrator.planner import IntelligentTaskPlanner
from logic.orchestrator.project_analyzer import GodotProjectAnalyzer


class TestAutonomousOrchestrator(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name)
        # Setup mock project structure
        (self.project_path / "project.godot").write_text("config_version=5\n[application]\nconfig/name=\"TestProject\"\n")
        (self.project_path / "scripts").mkdir()
        (self.project_path / "scenes").mkdir()

        # Existing script
        self.player_script = self.project_path / "scripts" / "player.gd"
        self.player_script.write_text("extends CharacterBody2D\n\nvar speed: float = 300.0\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_plan_persistence_and_serialization(self) -> None:
        """Verifies that ProjectPlan serializes to disk and reloads accurately."""
        task1 = TaskItem(
            id="t1",
            description="Create Coin scene",
            target_files=["scenes/coin.tscn"],
            acceptance_criteria=["Valid TSCN"],
            status=TaskStatus.PASSED,
        )
        task2 = TaskItem(
            id="t2",
            description="Create Coin script",
            target_files=["scripts/coin.gd"],
            dependencies=["t1"],
            status=TaskStatus.READY,
        )
        plan = ProjectPlan(
            plan_id="plan_123",
            user_request="Add a coin pickup item",
            project_path=str(self.project_path),
            is_complex=True,
            tasks=[task1, task2],
        )

        plan_file = self.project_path / ".godot_agent" / "plan.json"
        plan.save_to_disk(plan_file)
        self.assertTrue(plan_file.exists())

        loaded_plan = ProjectPlan.load_from_disk(plan_file)
        self.assertIsNotNone(loaded_plan)
        self.assertEqual(loaded_plan.plan_id, "plan_123")
        self.assertEqual(len(loaded_plan.tasks), 2)
        self.assertEqual(loaded_plan.tasks[0].status, TaskStatus.PASSED)
        self.assertEqual(loaded_plan.tasks[1].dependencies, ["t1"])

    def test_path_sanitization_rejects_traversal(self) -> None:
        """Verifies path traversal attacks like ../etc/passwd are strictly blocked."""
        # Clean relative path should succeed
        safe_path = sanitize_project_relative_path(self.project_path, "scripts/new_script.gd")
        self.assertEqual(safe_path, self.project_path / "scripts" / "new_script.gd")

        # Escaping path must raise PermissionError
        with self.assertRaises(PermissionError):
            sanitize_project_relative_path(self.project_path, "../outside.gd")

        with self.assertRaises(PermissionError):
            sanitize_project_relative_path(self.project_path, "../../etc/passwd")

    def test_planner_simple_vs_complex_decomposition(self) -> None:
        """Verifies simple requests stay 1 task while complex requests produce ordered DAGs."""
        planner = IntelligentTaskPlanner(self.project_path)

        # Simple request
        simple_plan = planner.plan_request("change player speed to 400.0")
        self.assertFalse(simple_plan.is_complex)
        self.assertEqual(len(simple_plan.tasks), 1)
        self.assertEqual(simple_plan.tasks[0].status, TaskStatus.READY)

        # Complex request with multiple features
        complex_plan = planner.plan_request(
            "Create a coin pickup system with animated coin scene, collection script, and audio sound"
        )
        self.assertTrue(complex_plan.is_complex)
        self.assertGreaterEqual(len(complex_plan.tasks), 2)
        # Ensure dependencies are ordered
        task_ids = [t.id for t in complex_plan.tasks]
        for task in complex_plan.tasks:
            for dep in task.dependencies:
                self.assertIn(dep, task_ids)
                self.assertLess(task_ids.index(dep), task_ids.index(task.id))

    def test_executor_successful_staging_and_diff(self) -> None:
        """Verifies TaskExecutor stages cleanly, computes unified diff, and commits."""
        new_content = "extends CharacterBody2D\n\nvar speed: float = 450.0\n\nfunc _physics_process(delta: float) -> void:\n\tmove_and_slide()\n"
        
        def mock_generator(msgs: list) -> str:
            return json.dumps({
                "thought": "Update speed and add physics process",
                "action_type": "create_or_update_script",
                "parameters": {
                    "file_path": "scripts/player.gd",
                    "content": new_content,
                },
            })

        executor = TaskExecutor(self.project_path, generator_fn=mock_generator)
        task = TaskItem(
            id="t_speed",
            description="Update player speed",
            target_files=["scripts/player.gd"],
        )

        res = executor.execute_task(task)
        self.assertTrue(res.success)
        self.assertEqual(res.status, TaskStatus.PASSED)
        self.assertIn("+var speed: float = 450.0", res.diff)
        self.assertEqual(self.player_script.read_text(encoding="utf-8"), new_content)

    def test_executor_bounded_repair_and_rollback_protection(self) -> None:
        """Verifies that invalid code triggers bounded repair attempts and never corrupts the original file on failure."""
        original_code = self.player_script.read_text(encoding="utf-8")
        generator_calls = 0

        def failing_generator(msgs: list) -> str:
            nonlocal generator_calls
            generator_calls += 1
            # Emits invalid GDScript with syntax error
            return json.dumps({
                "thought": "Emit broken script",
                "action_type": "create_or_update_script",
                "parameters": {
                    "file_path": "scripts/player.gd",
                    "content": "extends CharacterBody2D\n\nfunc bad_func(:\n\tpass",
                },
            })

        executor = TaskExecutor(self.project_path, generator_fn=failing_generator)
        task = TaskItem(
            id="t_broken",
            description="Attempt broken edit",
            target_files=["scripts/player.gd"],
            max_attempts=2,
        )

        res = executor.execute_task(task, max_repairs=2)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        # Must have attempted 3 times (initial + 2 repairs)
        self.assertEqual(generator_calls, 3)
        # CRITICAL: Original project file must NOT be corrupted!
        self.assertEqual(self.player_script.read_text(encoding="utf-8"), original_code)
        self.assertGreater(len(task.diagnostics), 0)

    def test_orchestrator_multi_task_dependency_and_resumption(self) -> None:
        """Verifies multi-task execution, dependency cascading on failure, and state resumption."""
        call_count = 0

        def mock_generator(msgs: list) -> str:
            nonlocal call_count
            call_count += 1
            last_prompt = msgs[-1]["content"]

            if "task_01" in last_prompt:
                return json.dumps({
                    "thought": "Create health resource",
                    "action_type": "create_or_update_script",
                    "parameters": {
                        "file_path": "scripts/health.gd",
                        "content": "class_name HealthComponent\nextends Node\n\n@export var max_health: int = 100\n",
                    },
                })
            else:
                return json.dumps({
                    "thought": "Create UI script",
                    "action_type": "create_or_update_script",
                    "parameters": {
                        "file_path": "scripts/health_bar.gd",
                        "content": "extends ProgressBar\n\nfunc update_bar(val: int) -> void:\n\tvalue = val\n",
                    },
                })

        orchestrator = AutonomousProjectOrchestrator(self.project_path, generator_fn=mock_generator)

        # Create two tasks where task_02 depends on task_01
        task1 = TaskItem(
            id="task_01",
            description="Create health component script",
            target_files=["scripts/health.gd"],
            dependencies=[],
        )
        task2 = TaskItem(
            id="task_02",
            description="Create health bar UI",
            target_files=["scripts/health_bar.gd"],
            dependencies=["task_01"],
        )
        plan = ProjectPlan(
            plan_id="plan_chain",
            user_request="Build health component and UI",
            project_path=str(self.project_path),
            is_complex=True,
            tasks=[task1, task2],
        )

        # 1. Execute task 1 manually, simulate interruption
        plan.save_to_disk(orchestrator.plan_file)
        res1 = orchestrator.executor.execute_task(task1)
        self.assertTrue(res1.success)
        task1.status = TaskStatus.PASSED
        plan.save_to_disk(orchestrator.plan_file)

        # 2. Resume execution from disk!
        # The orchestrator must NOT re-execute task 1, but continue with task 2
        initial_calls = call_count
        summary = orchestrator.resume_execution()
        self.assertEqual(summary["overall_status"], "completed")
        self.assertEqual(summary["passed_count"], 2)
        self.assertEqual(summary["failed_count"], 0)
        # Verifies task 1 was not regenerated during resumption
        self.assertEqual(call_count, initial_calls + 1)
        self.assertTrue((self.project_path / "scripts" / "health_bar.gd").exists())

    def test_cascading_blocked_status_when_prerequisite_fails(self) -> None:
        """Verifies that when task A fails, dependent task B is marked BLOCKED instead of executing."""
        def failing_task1_generator(msgs: list) -> str:
            return json.dumps({
                "thought": "Fail",
                "action_type": "create_or_update_script",
                "parameters": {
                    "file_path": "scripts/fail.gd",
                    "content": "invalid gdscript (: pass",
                },
            })

        orchestrator = AutonomousProjectOrchestrator(self.project_path, generator_fn=failing_task1_generator)
        task1 = TaskItem(
            id="task_core",
            description="Core dependency",
            target_files=["scripts/fail.gd"],
        )
        task2 = TaskItem(
            id="task_consumer",
            description="Dependent feature",
            target_files=["scripts/consumer.gd"],
            dependencies=["task_core"],
        )
        plan = ProjectPlan(
            plan_id="plan_cascade",
            user_request="Chain with failure",
            project_path=str(self.project_path),
            is_complex=True,
            tasks=[task1, task2],
        )
        plan.save_to_disk(orchestrator.plan_file)

        summary = orchestrator.execute_plan(plan, max_repairs_per_task=1)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["blocked_count"], 1)
        self.assertEqual(summary["passed_count"], 0)
        self.assertEqual(plan.tasks[1].status, TaskStatus.BLOCKED)
        self.assertIn("Blocked by prerequisite task 'task_core'", plan.tasks[1].diagnostics[0])


if __name__ == "__main__":
    unittest.main()
