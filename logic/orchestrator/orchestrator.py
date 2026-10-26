"""Autonomous Project-Building Orchestrator for Godot 4 AI Agent."""

from __future__ import annotations

from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional

from logic.orchestrator.executor import TaskExecutionResult, TaskExecutor
from logic.orchestrator.models import ProjectPlan, TaskItem, TaskStatus
from logic.orchestrator.planner import IntelligentTaskPlanner
from logic.orchestrator.project_analyzer import GodotProjectAnalyzer

logger = logging.getLogger("GodotAgentOrchestrator")


class AutonomousProjectOrchestrator:
    """Coordinates end-to-end planning, dependency-ordered execution, and resumable state persistence."""

    def __init__(
        self,
        project_path: Path,
        generator_fn: Optional[Callable[[List[Dict[str, str]]], str]] = None,
        godot_bin: Optional[str] = None,
    ):
        self.project_path = project_path.resolve()
        self.generator_fn = generator_fn
        self.godot_bin = godot_bin
        self.planner = IntelligentTaskPlanner(self.project_path, generator_fn=generator_fn)
        self.executor = TaskExecutor(self.project_path, generator_fn=generator_fn, godot_bin=godot_bin)
        self.analyzer = GodotProjectAnalyzer(self.project_path)
        self.plan_file = self.project_path / ".godot_agent" / "plan.json"

    def plan(self, user_request: str) -> ProjectPlan:
        """Analyzes project and creates a dependency-aware ProjectPlan, saving to disk."""
        plan = self.planner.plan_request(user_request)
        plan.save_to_disk(self.plan_file)
        return plan

    def get_current_plan(self) -> Optional[ProjectPlan]:
        """Loads existing plan from disk if available."""
        return ProjectPlan.load_from_disk(self.plan_file)

    def execute_plan(
        self,
        plan: Optional[ProjectPlan] = None,
        max_repairs_per_task: int = 2,
    ) -> Dict[str, Any]:
        """Executes the plan in dependency order with isolated validation and persistence."""
        if plan is None:
            plan = self.get_current_plan()
            if plan is None:
                raise ValueError("No plan provided and no existing plan found on disk.")

        plan.status = "executing"
        plan.updated_at = time.time()
        plan.save_to_disk(self.plan_file)

        task_map: Dict[str, TaskItem] = {t.id: t for t in plan.tasks}
        modified_files_set = set()

        max_iterations = len(plan.tasks) * 3 + 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Check if all tasks are in terminal states
            unfinished = [t for t in plan.tasks if t.status in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING)]
            if not unfinished:
                break

            # Find next ready task
            ready_tasks = []
            for t in plan.tasks:
                if t.status == TaskStatus.PASSED or t.status in (TaskStatus.FAILED, TaskStatus.BLOCKED):
                    continue

                # Check prerequisites
                deps_met = True
                dep_failed = False
                for dep_id in t.dependencies:
                    dep = task_map.get(dep_id)
                    if not dep or dep.status != TaskStatus.PASSED:
                        deps_met = False
                    if dep and dep.status in (TaskStatus.FAILED, TaskStatus.BLOCKED):
                        dep_failed = True
                        break

                if dep_failed:
                    t.status = TaskStatus.BLOCKED
                    t.diagnostics.append(f"Blocked by prerequisite task '{dep_id}' which did not pass.")
                    plan.execution_log.append({
                        "task_id": t.id,
                        "action": "blocked_by_dependency",
                        "dep_id": dep_id,
                        "timestamp": time.time(),
                    })
                    plan.save_to_disk(self.plan_file)
                    continue

                if deps_met:
                    t.status = TaskStatus.READY
                    ready_tasks.append(t)

            if not ready_tasks:
                # Deadlock detection: unfinished tasks exist but none can make progress
                for t in unfinished:
                    if t.status not in (TaskStatus.FAILED, TaskStatus.BLOCKED):
                        t.status = TaskStatus.BLOCKED
                        t.diagnostics.append("Blocked due to unresolvable dependency cycle or deadlock.")
                break

            # Execute the next ready task
            current_task = ready_tasks[0]
            current_task.status = TaskStatus.RUNNING
            plan.save_to_disk(self.plan_file)

            exec_result: TaskExecutionResult = self.executor.execute_task(
                current_task,
                max_repairs=max_repairs_per_task,
            )

            current_task.status = exec_result.status
            current_task.updated_at = time.time()
            if exec_result.diff:
                current_task.output_diff = exec_result.diff

            for mf in exec_result.modified_files:
                modified_files_set.add(mf)

            # Record in execution log
            plan.execution_log.append({
                "task_id": current_task.id,
                "status": exec_result.status.value,
                "attempts": exec_result.attempts,
                "modified_files": exec_result.modified_files,
                "error": exec_result.error,
                "elapsed_sec": exec_result.elapsed_sec,
                "timestamp": time.time(),
            })

            # Save state immediately after every task
            plan.updated_at = time.time()
            plan.save_to_disk(self.plan_file)

        # Final status determination
        has_failed = any(t.status in (TaskStatus.FAILED, TaskStatus.BLOCKED) for t in plan.tasks)
        all_passed = all(t.status == TaskStatus.PASSED for t in plan.tasks)

        if all_passed:
            plan.status = "completed"
        elif has_failed:
            plan.status = "blocked"
        else:
            plan.status = "interrupted"

        plan.updated_at = time.time()
        plan.save_to_disk(self.plan_file)

        return self.generate_execution_summary(plan, list(modified_files_set))

    def resume_execution(self, max_repairs_per_task: int = 2) -> Dict[str, Any]:
        """Resumes an interrupted or partially executed plan from disk."""
        plan = self.get_current_plan()
        if not plan:
            raise ValueError(f"No existing plan found at {self.plan_file} to resume.")

        # Reset any interrupted 'running' tasks to 'ready'
        for t in plan.tasks:
            if t.status == TaskStatus.RUNNING:
                t.status = TaskStatus.READY

        plan.save_to_disk(self.plan_file)
        return self.execute_plan(plan, max_repairs_per_task=max_repairs_per_task)

    def generate_execution_summary(
        self, plan: ProjectPlan, modified_files: List[str]
    ) -> Dict[str, Any]:
        """Produces a comprehensive execution report separating passed, failed, and blocked tasks."""
        passed_tasks = [t for t in plan.tasks if t.status == TaskStatus.PASSED]
        failed_tasks = [t for t in plan.tasks if t.status == TaskStatus.FAILED]
        blocked_tasks = [t for t in plan.tasks if t.status == TaskStatus.BLOCKED]
        pending_tasks = [t for t in plan.tasks if t.status in (TaskStatus.PENDING, TaskStatus.READY)]

        return {
            "plan_id": plan.plan_id,
            "overall_status": plan.status,
            "user_request": plan.user_request,
            "total_tasks": len(plan.tasks),
            "passed_count": len(passed_tasks),
            "failed_count": len(failed_tasks),
            "blocked_count": len(blocked_tasks),
            "pending_count": len(pending_tasks),
            "modified_files": modified_files,
            "tasks_summary": [
                {
                    "id": t.id,
                    "description": t.description,
                    "status": t.status.value,
                    "attempts": t.attempts,
                    "target_files": t.target_files,
                    "has_diff": bool(t.output_diff),
                    "diagnostics": t.diagnostics,
                }
                for t in plan.tasks
            ],
            "execution_log": plan.execution_log,
        }
