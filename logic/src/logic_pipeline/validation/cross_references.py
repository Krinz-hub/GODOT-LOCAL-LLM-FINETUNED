"""Cross-reference validation across scenes, scripts, tasks, and requirements."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class CrossReferenceReport:
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    unresolved_count: int = 0


def validate_cross_references(
    plan: Dict[str, Any],
    known_project_files: Optional[Set[str]] = None,
) -> CrossReferenceReport:
    """Validates relational integrity within a production logic plan."""
    report = CrossReferenceReport()
    known = {f.replace("res://", "").lstrip("/") for f in (known_project_files or set())}

    # 1. Map planned scene paths and script paths
    planned_scenes = set()
    planned_scripts = set()
    for sc in plan.get("scenes", []):
        p = sc.get("path", "").replace("res://", "").lstrip("/")
        if p:
            planned_scenes.add(p)
        s = (sc.get("script") or "").replace("res://", "").lstrip("/")
        if s:
            planned_scripts.add(s)

    for sys in plan.get("systems", []):
        sp = (sys.get("script_path") or "").replace("res://", "").lstrip("/")
        if sp:
            planned_scripts.add(sp)

    # 2. Check entry scene
    arch = plan.get("architecture", {})
    entry = arch.get("entry_scene", "").replace("res://", "").lstrip("/")
    if entry and entry not in planned_scenes and (known and entry not in known):
        report.warnings.append(f"Entry scene '{entry}' is neither planned nor exists in project files")
        report.unresolved_count += 1

    # 3. Check tasks and prerequisites
    tasks = plan.get("implementation_tasks", [])
    task_map = {t.get("id"): t for t in tasks if t.get("id")}

    for t in tasks:
        t_id = t.get("id")
        for prereq in t.get("prerequisites", []):
            if prereq not in task_map:
                report.errors.append(f"Task '{t_id}' requires non-existent prerequisite task '{prereq}'")
                report.is_valid = False
                report.unresolved_count += 1

    # 4. Check acceptance criteria link to real tasks
    for ac in plan.get("acceptance_criteria", []):
        v_task = ac.get("verified_by_task")
        if v_task and v_task not in task_map:
            report.warnings.append(f"Acceptance criterion '{ac.get('id')}' links to non-existent task '{v_task}'")
            report.unresolved_count += 1

    # 5. Check systems dependencies
    system_names = {sys.get("name") for sys in plan.get("systems", []) if sys.get("name")}
    for dep in plan.get("dependencies", []):
        comp = dep.get("component")
        dep_on = dep.get("depends_on")
        if comp and comp not in system_names and comp not in [s.get("name") for s in plan.get("scenes", [])]:
            report.warnings.append(f"Dependency component '{comp}' is not a declared scene or system")

    return report
