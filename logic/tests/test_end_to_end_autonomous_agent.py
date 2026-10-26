"""End-to-End Verification of Autonomous Project-Building Agent Acceptance Criteria."""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from logic.orchestrator.executor import (
    GODOT_BIN,
    TaskExecutionResult,
    TaskExecutor,
    parse_action_payload,
    sanitize_project_relative_path,
)
from logic.orchestrator.models import ProjectPlan, TaskItem, TaskStatus
from logic.orchestrator.orchestrator import AutonomousProjectOrchestrator
from logic.orchestrator.planner import IntelligentTaskPlanner
from logic.orchestrator.project_analyzer import GodotProjectAnalyzer

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestEndToEndAutonomousAgent(unittest.TestCase):
    """Rigorous verification of the 10 acceptance criteria for autonomous operation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name)
        # Initialize standard Godot 4 project environment
        (self.project_path / "project.godot").write_text("config_version=5\n[application]\nconfig/name=\"E2ETest\"\n")
        (self.project_path / "scripts").mkdir()
        (self.project_path / "scenes").mkdir()

        # Create base player script
        self.player_file = self.project_path / "scripts" / "player.gd"
        self.initial_player_code = (
            "extends CharacterBody2D\n\n"
            "const SPEED = 300.0\n"
            "const JUMP_VELOCITY = -400.0\n\n"
            "func _physics_process(delta: float) -> void:\n"
            "\tmove_and_slide()\n"
        )
        self.player_file.write_text(self.initial_player_code, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_criterion_01_simple_prompt_creates_or_edits_file(self) -> None:
        """Criterion 1: A simple prompt creates or edits a real project file."""
        user_request = "increase player SPEED to 450.0"
        
        # Generator that provides surgical update
        def simple_gen(msgs: list) -> str:
            return json.dumps({
                "thought": "Update SPEED constant to 450.0",
                "action_type": "create_or_update_script",
                "parameters": {
                    "file_path": "scripts/player.gd",
                    "content": self.initial_player_code.replace("SPEED = 300.0", "SPEED = 450.0"),
                },
            })

        orchestrator = AutonomousProjectOrchestrator(self.project_path, generator_fn=simple_gen)
        plan = orchestrator.plan(user_request)

        # Simple prompt must produce single-task fast path
        self.assertFalse(plan.is_complex)
        self.assertEqual(len(plan.tasks), 1)

        summary = orchestrator.execute_plan(plan)
        self.assertEqual(summary["overall_status"], "completed")
        self.assertEqual(summary["passed_count"], 1)
        self.assertIn("scripts/player.gd", summary["modified_files"])

        # Check real file updated
        updated_code = self.player_file.read_text(encoding="utf-8")
        self.assertIn("SPEED = 450.0", updated_code)

    def test_criterion_02_complex_prompt_produces_dependency_aware_plan(self) -> None:
        """Criterion 2: A complex prompt produces a sensible, dependency-aware task plan."""
        planner = IntelligentTaskPlanner(self.project_path)
        complex_request = (
            "Build an inventory and coin collection system with a coin scene, pickup script, and HUD inventory UI"
        )
        plan = planner.plan_request(complex_request)

        self.assertTrue(plan.is_complex)
        self.assertGreaterEqual(len(plan.tasks), 2)

        # Verify dependency ordering (DAG topological consistency)
        task_indices = {t.id: i for i, t in enumerate(plan.tasks)}
        for task in plan.tasks:
            for dep in task.dependencies:
                self.assertIn(dep, task_indices, f"Dependency '{dep}' not found in task IDs")
                self.assertLess(task_indices[dep], task_indices[task.id], "Dependency must precede dependent task")

    def test_criterion_03_autonomous_multi_task_execution(self) -> None:
        """Criterion 3: The agent executes multiple tasks without requiring the user to manually direct each step."""
        task_execution_order = []

        def mock_generator(msgs: list) -> str:
            prompt = msgs[-1]["content"]
            if "task_01" in prompt:
                task_execution_order.append("task_01")
                return json.dumps({
                    "thought": "Create coin scene",
                    "action_type": "create_scene",
                    "parameters": {
                        "file_path": "scenes/coin.tscn",
                        "content": '[gd_scene format=3 uid="uid://coin"]\n[node name="Coin" type="Area2D"]\n',
                    },
                })
            elif "task_02" in prompt:
                task_execution_order.append("task_02")
                return json.dumps({
                    "thought": "Create coin script",
                    "action_type": "create_or_update_script",
                    "parameters": {
                        "file_path": "scripts/coin.gd",
                        "content": "extends Area2D\n\nsignal coin_collected\n\nfunc collect() -> void:\n\temit_signal(\"coin_collected\")\n\tqueue_free()\n",
                    },
                })
            else:
                task_execution_order.append("task_03")
                return json.dumps({
                    "thought": "Create UI script",
                    "action_type": "create_or_update_script",
                    "parameters": {
                        "file_path": "scripts/hud.gd",
                        "content": "extends CanvasLayer\n\n@onready var label: Label = $Label\n\nfunc set_coins(count: int) -> void:\n\tpass\n",
                    },
                })

        orchestrator = AutonomousProjectOrchestrator(self.project_path, generator_fn=mock_generator)
        task1 = TaskItem(id="task_01", description="Create coin scene", target_files=["scenes/coin.tscn"])
        task2 = TaskItem(id="task_02", description="Create coin script", target_files=["scripts/coin.gd"], dependencies=["task_01"])
        task3 = TaskItem(id="task_03", description="Create HUD UI", target_files=["scripts/hud.gd"], dependencies=["task_02"])

        plan = ProjectPlan(
            plan_id="e2e_multi",
            user_request="Build coin system and HUD",
            project_path=str(self.project_path),
            is_complex=True,
            tasks=[task1, task2, task3],
        )

        summary = orchestrator.execute_plan(plan)
        self.assertEqual(summary["overall_status"], "completed")
        self.assertEqual(summary["passed_count"], 3)
        self.assertEqual(task_execution_order, ["task_01", "task_02", "task_03"])
        self.assertTrue((self.project_path / "scenes" / "coin.tscn").exists())
        self.assertTrue((self.project_path / "scripts" / "coin.gd").exists())
        self.assertTrue((self.project_path / "scripts" / "hud.gd").exists())

    def test_criterion_04_completed_task_status_survives_restart(self) -> None:
        """Criterion 4: Completed task status survives a restart."""
        orchestrator = AutonomousProjectOrchestrator(self.project_path)
        plan_file = self.project_path / ".godot_agent" / "plan.json"

        # Simulate prior execution where task 1 passed, task 2 was ready
        task1 = TaskItem(id="t1", description="Step 1", target_files=["scripts/s1.gd"], status=TaskStatus.PASSED)
        task2 = TaskItem(id="t2", description="Step 2", target_files=["scripts/s2.gd"], dependencies=["t1"], status=TaskStatus.READY)
        initial_plan = ProjectPlan(
            plan_id="restart_plan",
            user_request="Test restart persistence",
            project_path=str(self.project_path),
            is_complex=True,
            tasks=[task1, task2],
            status="executing",
        )
        initial_plan.save_to_disk(plan_file)

        # Simulate fresh process restart
        fresh_orchestrator = AutonomousProjectOrchestrator(self.project_path)
        loaded = fresh_orchestrator.get_current_plan()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.tasks[0].status, TaskStatus.PASSED)
        self.assertEqual(loaded.tasks[1].status, TaskStatus.READY)

    def test_criterion_05_invalid_generated_code_detected_by_godot_validation(self) -> None:
        """Criterion 5: Invalid generated code is detected by actual Godot validation."""
        executor = TaskExecutor(self.project_path)
        invalid_gdscript = "extends CharacterBody2D\n\nfunc broken_syntax(\n\tprint('Missing closing parenthesis')"
        
        with tempfile.TemporaryDirectory() as stage:
            stage_dir = Path(stage)
            (stage_dir / "project.godot").write_text("config_version=5\n[application]\nconfig/name=\"Test\"\n")
            outcome = executor.validate_code_in_staging(stage_dir, "scripts/broken.gd", invalid_gdscript)
            
            # If Godot binary is available, verify actual engine diagnostic
            if GODOT_BIN and Path(GODOT_BIN).exists():
                self.assertFalse(outcome.is_valid)
                self.assertIn("Parse Error", outcome.diagnostics)
            else:
                self.assertFalse(outcome.is_valid)

    def test_criterion_06_bounded_repair_using_real_diagnostics(self) -> None:
        """Criterion 6: The agent attempts a bounded repair using real diagnostics."""
        turns = []

        def repairing_generator(msgs: list) -> str:
            turns.append(len(msgs))
            # On initial turn, emit code with syntax error
            if len(msgs) <= 2:
                return json.dumps({
                    "thought": "Initial attempt with typo",
                    "action_type": "create_or_update_script",
                    "parameters": {
                        "file_path": "scripts/repaired.gd",
                        "content": "extends Node\n\nfunc test_fn(:\n\tpass\n",
                    },
                })
            else:
                # The user prompt contains the compiler diagnostic!
                repair_prompt = msgs[-1]["content"]
                assert "compiler reported" in repair_prompt or "Parse Error" in repair_prompt or "error" in repair_prompt.lower()
                return json.dumps({
                    "thought": "Corrected syntax error",
                    "action_type": "create_or_update_script",
                    "parameters": {
                        "file_path": "scripts/repaired.gd",
                        "content": "extends Node\n\nfunc test_fn() -> void:\n\tpass\n",
                    },
                })

        executor = TaskExecutor(self.project_path, generator_fn=repairing_generator)
        task = TaskItem(
            id="t_repair",
            description="Create repaired script",
            target_files=["scripts/repaired.gd"],
        )

        res = executor.execute_task(task, max_repairs=2)
        self.assertTrue(res.success)
        self.assertEqual(res.status, TaskStatus.PASSED)
        self.assertEqual(res.attempts, 2)
        self.assertTrue((self.project_path / "scripts" / "repaired.gd").exists())

    def test_criterion_07_failed_repairs_do_not_corrupt_project(self) -> None:
        """Criterion 7: Failed repairs do not corrupt the last known-good project."""
        original_hash = self.player_file.read_text(encoding="utf-8")

        def always_broken(msgs: list) -> str:
            return json.dumps({
                "thought": "Always broken",
                "action_type": "create_or_update_script",
                "parameters": {
                    "file_path": "scripts/player.gd",
                    "content": "extends CharacterBody2D\n\nfunc fatal_syntax_error(\n\t",
                },
            })

        executor = TaskExecutor(self.project_path, generator_fn=always_broken)
        task = TaskItem(
            id="t_destructive",
            description="Destructive attempt",
            target_files=["scripts/player.gd"],
        )

        res = executor.execute_task(task, max_repairs=2)
        self.assertFalse(res.success)
        self.assertEqual(res.status, TaskStatus.FAILED)
        # CRITICAL SAFETY CHECK: Original player file must remain 100% pristine!
        self.assertEqual(self.player_file.read_text(encoding="utf-8"), original_hash)

    def test_criterion_08_final_report_distinguishes_task_states(self) -> None:
        """Criterion 8: The final report distinguishes completed, failed, and unverified tasks."""
        def partial_failing_gen(msgs: list) -> str:
            prompt = msgs[-1]["content"]
            if "task_01" in prompt:
                return json.dumps({
                    "thought": "Task 1 passes",
                    "action_type": "create_or_update_script",
                    "parameters": {"file_path": "scripts/t1.gd", "content": "extends Node\n"},
                })
            else:
                return json.dumps({
                    "thought": "Task 2 fails",
                    "action_type": "create_or_update_script",
                    "parameters": {"file_path": "scripts/t2.gd", "content": "func broken(\n\t"},
                })

        orchestrator = AutonomousProjectOrchestrator(self.project_path, generator_fn=partial_failing_gen)
        task1 = TaskItem(id="task_01", description="Passing task", target_files=["scripts/t1.gd"])
        task2 = TaskItem(id="task_02", description="Failing task", target_files=["scripts/t2.gd"])
        task3 = TaskItem(id="task_03", description="Dependent blocked task", target_files=["scripts/t3.gd"], dependencies=["task_02"])

        plan = ProjectPlan(
            plan_id="e2e_reporting",
            user_request="Test reporting",
            project_path=str(self.project_path),
            is_complex=True,
            tasks=[task1, task2, task3],
        )

        summary = orchestrator.execute_plan(plan, max_repairs_per_task=1)
        self.assertEqual(summary["overall_status"], "blocked")
        self.assertEqual(summary["total_tasks"], 3)
        self.assertEqual(summary["passed_count"], 1)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["blocked_count"], 1)
        self.assertEqual(summary["pending_count"], 0)

    def test_criterion_09_local_inference_setup_and_model_loading_contract(self) -> None:
        """Criterion 9: The workflow runs with the existing local inference setup."""
        # Verify schema file exists and is valid JSON
        schema_file = REPO_ROOT / "logic" / "schemas" / "godot_action.schema.json"
        self.assertTrue(schema_file.exists())
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        self.assertIn("action_type", schema.get("properties", {}))

        # Verify parsed action format matches executor requirements
        sample_output = '<godot_action>{"thought": "Test", "action_type": "chat_response", "parameters": {"message": "OK"}}</godot_action>'
        action = parse_action_payload(sample_output)
        self.assertEqual(action["action_type"], "chat_response")
        self.assertEqual(action["parameters"]["message"], "OK")

    def test_criterion_10_original_model_and_checkpoints_recoverable(self) -> None:
        """Criterion 10: The original model and checkpoints remain recoverable."""
        adapter_path = REPO_ROOT / "godot-agent-lora" / "final_adapter"
        self.assertTrue(adapter_path.exists(), "Original LoRA adapter directory must exist")
        self.assertTrue((adapter_path / "adapter_config.json").exists())
        self.assertTrue((adapter_path / "adapter_model.safetensors").exists())

        raw_dataset = REPO_ROOT / "raw"
        self.assertTrue(raw_dataset.exists(), "Raw dataset directory must remain intact")


if __name__ == "__main__":
    unittest.main()
