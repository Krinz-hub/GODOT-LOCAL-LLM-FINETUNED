"""Intelligent Task Planning, Complexity Analysis, and Dependency-Aware Decomposition."""

from __future__ import annotations

import json
from pathlib import Path
import re
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from logic.orchestrator.models import ProjectPlan, TaskItem, TaskStatus
from logic.orchestrator.project_analyzer import GodotProjectAnalyzer

PLANNER_SYSTEM_PROMPT = """You are a senior Godot 4 technical architect and project planner.
Your job is to analyze user requests, inspect the Godot 4 project context, and produce a dependency-aware execution plan.

Rules:
1. For SIMPLE requests (modifying a single file or creating one script/scene), emit exactly 1 task. DO NOT overcomplicate simple tasks.
2. For COMPLEX requests (multi-system features, new mechanics with UI/Audio/Physics), decompose into 2-5 small, sequential or independent tasks.
3. For OPEN-ENDED requests (e.g. "inspect the project and make one safe improvement"), inspect the project scripts/scenes, choose ONE specific file, identify a concrete non-breaking improvement (e.g. expose hardcoded constant as @export, add fall speed clamp, or add null guards), and state the justification. Do NOT emit generic placeholders.
4. Every task MUST have:
   - "id": unique snake_case string (e.g. "task_01_coin_scene")
   - "description": clear, single objective
   - "target_files": list of relative file paths (e.g. ["scenes/coin.tscn", "scripts/coin.gd"])
   - "dependencies": list of prerequisite task IDs that must complete first
   - "acceptance_criteria": concrete validation points (e.g. "Script compiles without errors in Godot 4", "Area2D has CollisionShape2D child")
5. Order tasks logically: data/scene definitions first, scripts second, UI/integration last.
6. Output MUST be a valid JSON object matching:
{
  "is_complex": boolean,
  "summary": "Brief explanation of plan",
  "tasks": [
    {
      "id": "task_01_...",
      "description": "...",
      "target_files": ["..."],
      "dependencies": [],
      "acceptance_criteria": ["..."]
    }
  ]
}
"""


class IntelligentTaskPlanner:
    def __init__(self, project_path: Path, generator_fn: Optional[Callable[[List[Dict[str, str]]], str]] = None):
        self.project_path = project_path.resolve()
        self.analyzer = GodotProjectAnalyzer(self.project_path)
        self.generator_fn = generator_fn

    def is_obviously_simple_request(self, user_request: str) -> bool:
        """Determines if request is clearly single-step without invoking planner LLM."""
        req = user_request.lower().strip()
        # Single-file edits or simple actions
        if any(req.startswith(p) for p in ("fix ", "change ", "update ", "edit ", "rename ", "increase ", "decrease ", "set ", "adjust ")):
            if " then " not in req and not any(w in req for w in ("system", "manager", "inventory", "multi-step")):
                return True

        target_files = re.findall(r"([a-zA-Z0-9_\-/\\]+\.(?:gd|tscn|tres))", user_request)
        if len(target_files) == 1 and not any(w in req for w in ("system", "manager", "inventory", "pause", "multiple", "spawner")):
            return True

        if len(req.split()) <= 8 and not any(w in req for w in ("system", "manager", "inventory", "complete", "multi")):
            return True

        return False

    def plan_request(self, user_request: str) -> ProjectPlan:
        """Produces a validated, dependency-aware ProjectPlan for the given user request."""
        meta = self.analyzer.get_project_metadata()
        struct = self.analyzer.list_project_structure()

        # Check for fast-path simple requests
        if self.is_obviously_simple_request(user_request):
            target_files = self._infer_target_files(user_request, struct)
            task = TaskItem(
                id="task_01_execute_request",
                description=user_request,
                target_files=target_files,
                dependencies=[],
                acceptance_criteria=["Godot 4 compiler validation passes cleanly"],
                status=TaskStatus.READY,
            )
            plan = ProjectPlan(
                plan_id=f"plan_{int(time.time())}",
                user_request=user_request,
                project_path=str(self.project_path),
                is_complex=False,
                tasks=[task],
                status="planning",
            )
            self._persist_plan(plan)
            return plan

        # Complex or multi-step request: Invoke planner model or heuristic decomposer
        context = self.analyzer.build_focused_context_for_task(
            target_files=struct["scripts"][:3] + struct["scenes"][:3],
            task_description=user_request,
        )

        plan_data = None
        if self.generator_fn is not None:
            messages = [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"User Request: {user_request}\n\nProject Context:\n{context}\n\nProduce the execution plan JSON.",
                },
            ]
            try:
                raw_plan = self.generator_fn(messages)
                plan_data = self._parse_planner_output(raw_plan)
            except Exception:
                plan_data = None

        if not plan_data:
            # Fallback to robust deterministic decomposition
            plan_data = self._heuristic_decomposition(user_request, struct)

        tasks: List[TaskItem] = []
        task_ids = set()
        for idx, t_raw in enumerate(plan_data.get("tasks", [])):
            t_id = t_raw.get("id") or f"task_{idx+1:02d}"
            # Ensure unique ID
            base_id = t_id
            c = 1
            while t_id in task_ids:
                t_id = f"{base_id}_{c}"
                c += 1
            task_ids.add(t_id)

            deps = [d for d in t_raw.get("dependencies", []) if d in task_ids and d != t_id]
            # Tasks with no dependencies start READY, others PENDING
            initial_status = TaskStatus.READY if not deps else TaskStatus.PENDING

            item = TaskItem(
                id=t_id,
                description=t_raw.get("description", f"Execute step {idx+1}"),
                target_files=t_raw.get("target_files", []),
                dependencies=deps,
                acceptance_criteria=t_raw.get("acceptance_criteria", ["Godot 4 syntax check passes"]),
                status=initial_status,
            )
            tasks.append(item)

        # Validate DAG (ensure no circular dependencies)
        tasks = self._topological_sort_tasks(tasks)

        plan = ProjectPlan(
            plan_id=f"plan_{int(time.time())}",
            user_request=user_request,
            project_path=str(self.project_path),
            is_complex=plan_data.get("is_complex", len(tasks) > 1),
            tasks=tasks,
            status="planning",
        )
        self._persist_plan(plan)
        return plan

    def _persist_plan(self, plan: ProjectPlan) -> None:
        plan_file = self.project_path / ".godot_agent" / "plan.json"
        plan.save_to_disk(plan_file)

    def _parse_planner_output(self, text: str) -> Optional[Dict[str, Any]]:
        cleaned = text.strip()
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        candidate = fence_match.group(1).strip() if fence_match else cleaned
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start : end + 1]
        try:
            d = json.loads(candidate)
            if isinstance(d, dict) and "tasks" in d and isinstance(d["tasks"], list):
                return d
        except Exception:
            pass
        return None

    def _infer_target_files(self, request: str, struct: Dict[str, List[str]]) -> List[str]:
        """Extracts mentioned or inferred file paths from request."""
        files = []
        for m in re.findall(r"([a-zA-Z0-9_\-/\\]+\.(?:gd|tscn|tres))", request):
            files.append(m)

        if not files:
            req_l = request.lower()
            if "player" in req_l:
                p_files = [f for f in struct["scripts"] if "player" in f.lower()]
                if p_files:
                    files.extend(p_files[:1])
            elif "enemy" in req_l:
                e_files = [f for f in struct["scripts"] if "enemy" in f.lower()]
                if e_files:
                    files.extend(e_files[:1])
            elif "coin" in req_l or "collect" in req_l:
                files.append("scenes/coin.tscn")
                files.append("scripts/coin.gd")

        return files

    def _heuristic_decomposition(self, request: str, struct: Dict[str, List[str]]) -> Dict[str, Any]:
        """Deterministic fallback decomposition for multi-system requests."""
        req_l = request.lower()
        tasks = []

        if any(w in req_l for w in ("inspect", "audit", "find safe", "safe improvement")) and ("safe" in req_l or "improve" in req_l):
            opp = self.analyzer.find_safe_improvement_opportunities()
            target_f = opp["target_file"]
            tasks.append({
                "id": "task_01_safe_improvement",
                "description": f"{opp['improvement_name']} in {target_f}: {opp['justification']}",
                "target_files": [target_f],
                "dependencies": [],
                "acceptance_criteria": opp["acceptance_criteria"],
            })
            tasks.append({
                "id": "task_02_integration_verification",
                "description": f"Validate project integrity and compiler checks after modifying {target_f}",
                "target_files": [target_f],
                "dependencies": ["task_01_safe_improvement"],
                "acceptance_criteria": ["Godot 4 engine headless validation passes with 0 errors"],
            })
            return {
                "is_complex": True,
                "summary": f"Inspected project and identified justified improvement: {opp['improvement_name']} on {target_f}",
                "tasks": tasks,
            }
        elif "coin" in req_l or "pickup" in req_l or "collect" in req_l:
            tasks.append({
                "id": "task_01_pickup_scene",
                "description": "Create pickup scene (scenes/coin.tscn) with Area2D and CollisionShape2D",
                "target_files": ["scenes/coin.tscn"],
                "dependencies": [],
                "acceptance_criteria": ["Area2D root with collision shape"],
            })
            tasks.append({
                "id": "task_02_pickup_script",
                "description": "Create pickup logic (scripts/coin.gd) with collection detection and signal",
                "target_files": ["scripts/coin.gd"],
                "dependencies": ["task_01_pickup_scene"],
                "acceptance_criteria": ["Valid Godot 4 GDScript, signal coin_collected"],
            })
            tasks.append({
                "id": "task_03_hud_counter",
                "description": "Update or create HUD coin counter display",
                "target_files": ["gui/coins_counter.gd"],
                "dependencies": ["task_02_pickup_script"],
                "acceptance_criteria": ["Updates UI label on signal"],
            })
        elif "pause" in req_l:
            tasks.append({
                "id": "task_01_pause_menu_scene",
                "description": "Create or update pause menu scene (gui/pause_menu.tscn) with resume and restart buttons",
                "target_files": ["gui/pause_menu.tscn"],
                "dependencies": [],
                "acceptance_criteria": ["Control root with resume and restart buttons", "Valid Godot 4 TSCN"],
            })
            tasks.append({
                "id": "task_02_pause_script",
                "description": "Implement pause controller script (gui/pause_menu.gd) handling pause toggle, process_mode, and button signals",
                "target_files": ["gui/pause_menu.gd"],
                "dependencies": ["task_01_pause_menu_scene"],
                "acceptance_criteria": ["Godot 4 compiler validation passes", "Handles tree pausing and button pressed events"],
            })
            tasks.append({
                "id": "task_03_pause_integration",
                "description": "Integrate pause menu into main game scene or controller",
                "target_files": ["game.gd"],
                "dependencies": ["task_02_pause_script"],
                "acceptance_criteria": ["Godot 4 headless validation passes cleanly"],
            })
        elif "spawner" in req_l or "wave" in req_l:
            tasks.append({
                "id": "task_01_spawner_script",
                "description": "Create wave spawner controller script (scripts/enemy_spawner.gd)",
                "target_files": ["scripts/enemy_spawner.gd"],
                "dependencies": [],
                "acceptance_criteria": ["Timer-based spawning logic in Godot 4"],
            })
            tasks.append({
                "id": "task_02_spawner_scene",
                "description": "Create enemy spawner scene (scenes/enemy_spawner.tscn) with Timer node",
                "target_files": ["scenes/enemy_spawner.tscn"],
                "dependencies": ["task_01_spawner_script"],
                "acceptance_criteria": ["Valid TSCN with attached spawner script"],
            })
        else:
            # Generic two-phase decomposition
            target_files = self._infer_target_files(request, struct)
            tasks.append({
                "id": "task_01_core_implementation",
                "description": f"Implement core functionality for: {request[:60]}",
                "target_files": target_files[:2] if target_files else ["scripts/game_feature.gd"],
                "dependencies": [],
                "acceptance_criteria": ["Godot 4 compiler validation passes"],
            })
            tasks.append({
                "id": "task_02_integration_verification",
                "description": f"Verify integration and attach signals for {request[:60]}",
                "target_files": target_files[2:] if len(target_files) > 2 else target_files[:1],
                "dependencies": ["task_01_core_implementation"],
                "acceptance_criteria": ["Clean Godot 4 check-only validation"],
            })

        return {"is_complex": True, "summary": f"Decomposed into {len(tasks)} steps", "tasks": tasks}

    def _topological_sort_tasks(self, tasks: List[TaskItem]) -> List[TaskItem]:
        """Sorts tasks by dependencies and breaks any cycles safely."""
        task_map = {t.id: t for t in tasks}
        visited: Set[str] = set()
        temp: Set[str] = set()
        order: List[TaskItem] = []

        def visit(task_id: str):
            if task_id in temp:
                # Cycle detected: break dependency
                task_map[task_id].dependencies = []
                return
            if task_id not in visited:
                temp.add(task_id)
                t = task_map.get(task_id)
                if t:
                    for dep in list(t.dependencies):
                        if dep in task_map:
                            visit(dep)
                temp.remove(task_id)
                visited.add(task_id)
                if t:
                    order.append(t)

        for t in tasks:
            if t.id not in visited:
                visit(t.id)

        return order
