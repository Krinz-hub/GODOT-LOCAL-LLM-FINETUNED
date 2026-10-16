"""Evidence validation and grounding checker."""

from typing import Any, Dict, List, Set, Tuple


def verify_evidence_grounding(
    plan: Dict[str, Any],
    project_files: Set[str],
) -> Tuple[bool, List[str]]:
    """Checks whether scenes, scripts, and tasks in a plan match ground-truth source evidence."""
    issues = []
    clean_files = {f.replace("res://", "").lstrip("/") for f in project_files}

    # Verify declared scenes against real files
    for sc in plan.get("scenes", []):
        sc_path = sc.get("path", "").replace("res://", "").lstrip("/")
        if sc_path and clean_files and sc_path not in clean_files:
            issues.append(f"Scene path '{sc_path}' not found in source evidence (marked planned/synthetic)")

        sc_script = (sc.get("script") or "").replace("res://", "").lstrip("/")
        if sc_script and clean_files and sc_script not in clean_files:
            issues.append(f"Script path '{sc_script}' for scene '{sc.get('name')}' not found in source evidence")

    # Verify systems
    for sys in plan.get("systems", []):
        s_path = (sys.get("script_path") or "").replace("res://", "").lstrip("/")
        if s_path and clean_files and s_path not in clean_files:
            issues.append(f"System script '{s_path}' not grounded in source evidence")

    # Verify implementation tasks don't reference non-existent files
    for t in plan.get("implementation_tasks", []):
        for f in t.get("files", []):
            clean_f = f.replace("res://", "").lstrip("/")
            # Tasks can create new planned files, which is normal for proposals,
            # but we flag if marked as verified without existence
            if t.get("status") == "verified" and clean_files and clean_f not in clean_files:
                issues.append(f"Task '{t.get('id')}' marked verified but file '{clean_f}' does not exist on disk")

    is_grounded = len(issues) == 0
    return is_grounded, issues
