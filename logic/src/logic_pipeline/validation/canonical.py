"""Canonical validator directly reflecting dev/validate.py and dev/lib.py.

Validates the 14-key production-logic plans against all topological,
schema, Godot 4 syntax, and referential integrity constraints.
"""

import json
from typing import Any, Dict, List, Set, Tuple

SCHEMA_KEYS = [
    "project_summary",
    "assumptions",
    "requirements",
    "gameplay_loop",
    "architecture",
    "scenes",
    "systems",
    "dependencies",
    "implementation_tasks",
    "acceptance_criteria",
    "risks",
    "verification_plan",
    "failure_analysis",
    "execution_state",
]

SYSTEM_PROMPT = (
    "You are a Godot game-production planning agent. Produce coherent, "
    "dependency-aware, testable game plans. Distinguish assumptions, proposed "
    "actions, and verified results."
)

EXECUTION_STATE = "plan_only_no_actions_executed"

GODOT3_BAD_PATTERNS = [
    "KinematicBody",
    "Spatial",
    "yield(",
    "onready var",
    "setget",
    "rset",
    "remote func",
    "NetworkedMultiplayerENet",
    "move_and_slide_with_snap",
    "OS.get_ticks",
    "instance()",
]

PLACEHOLDERS = [
    "TODO",
    "TBD",
    "implement the rest",
    "add more features",
    "lorem",
]

STATUS_OK = {"not_run", "passed", "failed", "blocked"}


def has_cycle(graph: Dict[str, List[str]]) -> bool:
    """Checks for cycles in directed graph."""
    state: Dict[str, int] = {}

    def visit(n: str) -> bool:
        if state.get(n) == 1:
            return True
        if state.get(n) == 2:
            return False
        state[n] = 1
        for m in graph.get(n, []):
            if visit(m):
                return True
        state[n] = 2
        return False

    return any(visit(n) for n in graph)


def check_canonical_plan(p: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Checks plan against all rules defined in dev/validate.py.
    
    Returns:
        (is_valid, list_of_errors)
    """
    errs: List[str] = []

    # 1. Schema keys check
    for k in SCHEMA_KEYS:
        if k not in p:
            errs.append(f"missing key {k}")
    if errs:
        return False, errs

    # 2. Tasks validation
    tasks = p.get("implementation_tasks", [])
    ids = [t.get("id") for t in tasks if isinstance(t, dict)]
    if len(ids) != len(set(ids)):
        errs.append("duplicate task ids")
    idset = set(ids)

    graph: Dict[str, List[str]] = {}
    for i, t in enumerate(tasks):
        t_id = t.get("id", f"task_{i}")
        prereqs = t.get("prerequisites", [])
        for pre in prereqs:
            if pre not in idset:
                errs.append(f"{t_id}: unknown prerequisite {pre}")
            elif ids.index(pre) >= i:
                errs.append(f"{t_id}: prerequisite {pre} listed later")
        graph[t_id] = prereqs
        if t.get("status") != "proposed":
            errs.append(f"{t_id}: status must be proposed")
        for f in t.get("files", []):
            if not f.startswith("res://"):
                errs.append(f"{t_id}: file not res:// {f}")

    if has_cycle(graph):
        errs.append("task graph cycle")

    task_files = {f for t in tasks for f in t.get("files", [])}

    # 3. Scene coverage and hierarchy
    for s in p.get("scenes", []):
        s_path = s.get("path", "")
        if s_path not in task_files:
            errs.append(f"scene {s_path} not produced/modified by any task")

        hierarchy = s.get("hierarchy", [])
        root_type = s.get("root_type", "")
        if not hierarchy or not isinstance(hierarchy, list):
            errs.append(f"scene {s.get('name')}: hierarchy must be a list of strings")
        else:
            first_line = hierarchy[0].rstrip()
            expected_tag = f"({root_type})"
            if not first_line.endswith(expected_tag) and expected_tag not in first_line:
                errs.append(f"scene {s.get('name')}: hierarchy root != root_type")

        s_script = s.get("script")
        if s_script and s_script not in task_files:
            errs.append(f"scene script {s_script} not in any task")

    # 4. System scripts coverage
    for s in p.get("systems", []):
        sp = s.get("script_path", "")
        if sp not in task_files:
            errs.append(f"system script {sp} not in any task")

    # 5. Architecture coverage
    arch = p.get("architecture", {})
    entry = arch.get("entry_scene", "")
    if entry not in task_files:
        errs.append("entry scene not in any task")

    autoloads = arch.get("autoloads", [])
    if isinstance(autoloads, list):
        for a in autoloads:
            if isinstance(a, dict):
                a_path = a.get("path", "")
                if a_path not in task_files:
                    errs.append(f"autoload {a_path} not in any task")
            else:
                errs.append(f"autoload entry must be a dictionary with 'path', got {type(a)}")
    else:
        errs.append(f"autoloads must be a list of dictionaries, got {type(autoloads)}")

    # 6. Acceptance criteria
    acs = p.get("acceptance_criteria", [])
    acids = [a.get("id") for a in acs if isinstance(a, dict)]
    if len(acids) != len(set(acids)):
        errs.append("duplicate acceptance ids")
    for a in acs:
        a_id = a.get("id", "")
        v_task = a.get("verified_by_task")
        if v_task not in idset:
            errs.append(f"{a_id}: verified_by_task unknown")
        if a.get("status") not in STATUS_OK or a.get("status") != "not_run":
            errs.append(f"{a_id}: status must be not_run")

    # 7. Verification plan
    for v in p.get("verification_plan", []):
        if v.get("status") != "not_run":
            errs.append("verification step status must be not_run")

    # 8. Failure analysis
    for fa in p.get("failure_analysis", []):
        if fa.get("repair_status") != "proposed" or fa.get("cause_status") != "hypothesis_unconfirmed":
            errs.append("failure_analysis must stay proposed/hypothesis")

    # 9. Execution state
    if p.get("execution_state") != EXECUTION_STATE:
        errs.append(f"execution_state wrong: expected '{EXECUTION_STATE}', got '{p.get('execution_state')}'")

    # 10. Non-empty fields
    for name in ("requirements", "gameplay_loop", "risks", "assumptions"):
        val = p.get(name)
        if not val:
            errs.append(f"{name} empty")

    # 11. Godot 3 patterns & placeholders
    blob = json.dumps(p)
    for bad in GODOT3_BAD_PATTERNS:
        if bad in blob:
            errs.append(f"Godot3 pattern: {bad}")
    blob_lower = blob.lower()
    for ph in PLACEHOLDERS:
        if ph.lower() in blob_lower:
            errs.append(f"placeholder: {ph}")

    return len(errs) == 0, errs
