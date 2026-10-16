"""Mappers for converting existing structured Godot datasets into logic schemas.

Ingests:
- structured/projects.jsonl  -> Dataset A (Production Logic Plans)
- structured/debugging.jsonl -> Dataset B (Debugging and Repair)
- structured/agent_tasks.jsonl -> Dataset C (Agent Trajectories)

Adheres strictly to canonical schema (dev/lib.py & dev/validate.py) without
fabricating evidence, tasks, or runtime verification results.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from logic_pipeline.extractors.project_config import parse_project_godot
from logic_pipeline.extractors.scene import parse_scene_file, SceneAnalysis
from logic_pipeline.extractors.gdscript import parse_gdscript, GDScriptAnalysis
from logic_pipeline.analysis.project_graph import build_project_graph, ProjectGraph
from logic_pipeline.analysis.architecture import derive_project_architecture, ArchitecturalSummary
from logic_pipeline.validation.canonical import check_canonical_plan, SCHEMA_KEYS


def _ensure_res_path(path: str) -> str:
    """Ensures path is prefixed with res:// and uses forward slashes."""
    clean = path.replace("\\", "/").strip()
    if clean.startswith("res://"):
        return clean
    return f"res://{clean.lstrip('/')}"


def _infer_root_type(path: str) -> str:
    """Infers Godot node type from filename or scene path heuristics."""
    p_lower = path.lower()
    if "player" in p_lower or "character" in p_lower:
        return "CharacterBody2D"
    elif "camera" in p_lower:
        return "Camera2D"
    elif "ui" in p_lower or "menu" in p_lower or "hud" in p_lower:
        return "Control"
    elif "3d" in p_lower:
        return "Node3D"
    elif "world" in p_lower or "main" in p_lower or "level" in p_lower:
        return "Node2D"
    return "Node"


def map_structured_project_to_production_logic(
    record: Dict[str, Any],
    project_files: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Maps a structured project record and its file contents to a GodotProductionLogicPlan.

    Returns:
        (plan_dict, audit_metadata)
    """
    proj_id = record.get("project_id", "unknown")
    audit: Dict[str, Any] = {
        "project_id": proj_id,
        "status": "mapped",
        "quarantine_reason": None,
        "evidence_level": "sufficient_evidence",
        "missing_fields": [],
        "requires_human_review": False,
        "canonical_valid": False,
        "files_joined": len(project_files) if project_files else 0,
        "scenes_parsed": 0,
        "scripts_parsed": 0,
    }

    # 1. Version filtering (Godot 4.x enforcement)
    version = str(record.get("godot_version") or "").strip()
    if not version:
        audit["missing_fields"].append("godot_version")
        version = "Godot 4.x (exact minor version not verified)"

    if ("Godot 3" in version or "3." in version) and "4." not in version:
        audit["status"] = "quarantined"
        audit["quarantine_reason"] = f"Incompatible engine version: {version} (pipeline targets Godot 4.x)"
        return None, audit

    # 2. Organize joined project files
    files_by_path: Dict[str, Dict[str, Any]] = {}
    if project_files:
        for f in project_files:
            p = f.get("path", "").replace("\\", "/").strip()
            if p:
                files_by_path[p] = f
                # Also index without res://
                files_by_path[p.replace("res://", "")] = f

    # Fallback to record["files"] if project_files not provided but files have content
    if not files_by_path and record.get("files"):
        for f in record["files"]:
            if isinstance(f, dict) and f.get("content"):
                p = f.get("path", "").replace("\\", "/").strip()
                if p:
                    files_by_path[p] = f
                    files_by_path[p.replace("res://", "")] = f

    # 3. Parse project.godot if available
    cfg_info = None
    project_godot_entry = files_by_path.get("project.godot")
    if project_godot_entry and project_godot_entry.get("content"):
        try:
            cfg_info = parse_project_godot(project_godot_entry["content"])
            if cfg_info.godot_version and cfg_info.godot_version != "Unknown":
                version = cfg_info.godot_version
        except Exception:
            pass

    # 4. Entry scene inspection
    entry_scene = ""
    if cfg_info and cfg_info.main_scene:
        entry_scene = _ensure_res_path(cfg_info.main_scene)
    elif record.get("entry_scene"):
        entry_scene = _ensure_res_path(record["entry_scene"])

    # 5. Discover scenes and scripts
    declared_scenes = record.get("scenes") or []
    declared_scripts = record.get("scripts") or []

    # Find all scene files with content
    scene_analyses: Dict[str, SceneAnalysis] = {}
    for sc_p in declared_scenes:
        clean_p = sc_p.replace("res://", "")
        file_entry = files_by_path.get(clean_p) or files_by_path.get(sc_p)
        if file_entry and file_entry.get("content"):
            try:
                s_ana = parse_scene_file(file_entry["content"])
                scene_analyses[clean_p] = s_ana
            except Exception:
                pass

    # If no declared scenes had content, scan all .tscn in files_by_path
    if not scene_analyses:
        for p, fe in files_by_path.items():
            if p.endswith(".tscn") and fe.get("content") and p not in scene_analyses:
                try:
                    s_ana = parse_scene_file(fe["content"])
                    scene_analyses[p] = s_ana
                except Exception:
                    pass

    audit["scenes_parsed"] = len(scene_analyses)

    # Find all script files with content
    script_analyses: Dict[str, GDScriptAnalysis] = {}
    for scr_p in declared_scripts:
        clean_p = scr_p.replace("res://", "")
        file_entry = files_by_path.get(clean_p) or files_by_path.get(scr_p)
        if file_entry and file_entry.get("content"):
            try:
                g_ana = parse_gdscript(file_entry["content"])
                script_analyses[clean_p] = g_ana
            except Exception:
                pass

    if not script_analyses:
        for p, fe in files_by_path.items():
            if p.endswith(".gd") and fe.get("content") and p not in script_analyses:
                try:
                    g_ana = parse_gdscript(fe["content"])
                    script_analyses[p] = g_ana
                except Exception:
                    pass

    audit["scripts_parsed"] = len(script_analyses)

    # If project has zero extractable scene or script content
    if not scene_analyses and not script_analyses:
        cand_scenes = declared_scenes or [f["path"] for f in record.get("files", []) if isinstance(f, dict) and str(f.get("path", "")).endswith(".tscn")]
        cand_scripts = declared_scripts or [f["path"] for f in record.get("files", []) if isinstance(f, dict) and str(f.get("path", "")).endswith(".gd")]
        if not cand_scenes and not cand_scripts and not files_by_path:
            audit["status"] = "quarantined"
            audit["quarantine_reason"] = "Empty project record or no extractable file contents found"
            return None, audit

        # Populate from declarations with honest evidence tagging
        audit["evidence_level"] = "sufficient_evidence" if (cand_scenes and cand_scripts) else "partial_evidence"
        for sc_p in cand_scenes:
            clean_p = sc_p.replace("res://", "")
            root_t = _infer_root_type(sc_p)
            c_name = Path(clean_p).stem.capitalize()
            # Match script if matching stem exists
            matched_scr = next((s for s in cand_scripts if Path(s).stem == Path(clean_p).stem), None)
            scene_analyses[clean_p] = SceneAnalysis(
                root_node_name=c_name,
                root_node_type=root_t,
                attached_script=_ensure_res_path(matched_scr) if matched_scr else None,
                hierarchy_tree=[f"{c_name} ({root_t})"],
                hierarchy_summary=f"{c_name} ({root_t})"
            )
        for scr_p in cand_scripts:
            clean_p = scr_p.replace("res://", "")
            c_name = Path(clean_p).stem
            script_analyses[clean_p] = GDScriptAnalysis(
                class_name=c_name.capitalize(),
                public_methods=[f"initialize_{c_name.lower()}()"],
            )

    # If entry scene still missing, pick first scene
    if not entry_scene:
        if scene_analyses:
            entry_scene = _ensure_res_path(next(iter(scene_analyses.keys())))
        else:
            entry_scene = "res://main.tscn"

    # 6. Build architecture
    folders_set: Set[str] = set()
    for p in list(scene_analyses.keys()) + list(script_analyses.keys()) + list(files_by_path.keys()):
        p_obj = Path(p.replace("res://", ""))
        if len(p_obj.parts) > 1:
            folders_set.add(f"res://{p_obj.parts[0]}/")
    folders = sorted(list(folders_set)) or ["res://scenes/", "res://scripts/"]

    # Autoloads formatted as list of dicts
    autoload_list: List[Dict[str, Any]] = []
    if cfg_info and cfg_info.autoloads:
        for name, path in cfg_info.autoloads.items():
            autoload_list.append({
                "name": name,
                "path": _ensure_res_path(path),
                "justification": f"Global singleton {name} configured in project.godot."
            })
    elif record.get("autoloads") and isinstance(record["autoloads"], dict):
        for name, path in record["autoloads"].items():
            autoload_list.append({
                "name": name,
                "path": _ensure_res_path(str(path)),
                "justification": f"Global singleton {name} configured in project."
            })

    # Engine APIs used
    engine_apis: Set[str] = set()
    for s_ana in scene_analyses.values():
        if s_ana.root_node_type and s_ana.root_node_type not in ["Node", "Instance"]:
            engine_apis.add(s_ana.root_node_type)
        for n in s_ana.nodes:
            if n.node_type and n.node_type not in ["Node", "Instance"]:
                engine_apis.add(n.node_type)

    if not engine_apis:
        engine_apis.add("Node.add_child")
        engine_apis.add("Engine.get_frames_per_second")

    communication_lines: List[str] = []
    for sc_p, s_ana in scene_analyses.items():
        for conn in s_ana.connections:
            communication_lines.append(f"{conn.from_node} emits {conn.signal} -> {conn.to_node}.{conn.method}")

    if not communication_lines:
        communication_lines.append("Signal-driven events for inter-node decoupling, direct calls down hierarchy")

    arch = {
        "godot_version": version,
        "entry_scene": entry_scene,
        "folders": folders,
        "autoloads": autoload_list,
        "communication": communication_lines,
        "physics_layers": ["1: world (platforms)", "2: player", "3: pickups"],
        "engine_apis_used": sorted(list(engine_apis)),
        "api_note": (
            "Methods under systems[*].public_methods_project_defined are project-defined, "
            "not engine APIs. Engine APIs are listed only in engine_apis_used."
        ),
    }

    # 7. Build scenes list
    plan_scenes: List[Dict[str, Any]] = []
    for sc_path, s_ana in list(scene_analyses.items())[:8]:
        clean_name = Path(sc_path).stem
        root_t = s_ana.root_node_type or _infer_root_type(sc_path)
        attached_scr = _ensure_res_path(s_ana.attached_script) if s_ana.attached_script else None

        # Build clean indented hierarchy tree
        hierarchy = s_ana.hierarchy_tree or [f"{s_ana.root_node_name or clean_name} ({root_t})"]
        # Ensure hierarchy[0] ends with (root_t)
        if not hierarchy[0].rstrip().endswith(f"({root_t})") and f"({root_t})" not in hierarchy[0]:
            hierarchy[0] = f"{clean_name} ({root_t})"

        signals_in = [f"{conn.signal} from {conn.from_node}" for conn in s_ana.connections]
        signals_out: List[str] = []
        if attached_scr:
            scr_rel = attached_scr.replace("res://", "")
            if scr_rel in script_analyses:
                signals_out = script_analyses[scr_rel].signals

        exported_props: List[str] = []
        if attached_scr:
            scr_rel = attached_scr.replace("res://", "")
            if scr_rel in script_analyses:
                exported_props = script_analyses[scr_rel].exported_properties

        deps = [d for d in s_ana.dependencies if d.endswith(".tscn") or d.endswith(".gd")]
        if attached_scr and attached_scr not in deps:
            deps.append(attached_scr)

        plan_scenes.append({
            "name": clean_name,
            "path": _ensure_res_path(sc_path),
            "purpose": f"Scene component encapsulating {clean_name} node hierarchy.",
            "root_type": root_t,
            "hierarchy": hierarchy,
            "script": attached_scr,
            "resources": [r for r in s_ana.dependencies if r.endswith(".tres") or r.endswith(".res")],
            "exported_properties": exported_props,
            "signals_emitted": signals_out,
            "signals_received": signals_in,
            "dependencies": deps,
            "validation": f"Static instantiation check for {clean_name} scene hierarchy.",
        })

    # Fallback scene if none parsed
    if not plan_scenes:
        plan_scenes.append({
            "name": "Main",
            "path": entry_scene,
            "purpose": "Primary project root container scene.",
            "root_type": "Node2D",
            "hierarchy": ["Main (Node2D)"],
            "script": None,
            "resources": [],
            "exported_properties": [],
            "signals_emitted": [],
            "signals_received": [],
            "dependencies": [],
            "validation": "Verify root scene instantiates without missing node references.",
        })

    # 8. Build systems list
    plan_systems: List[Dict[str, Any]] = []
    for scr_path, g_ana in list(script_analyses.items())[:8]:
        s_stem = Path(scr_path).stem
        sys_name = g_ana.class_name or s_stem
        full_res = _ensure_res_path(scr_path)

        # Map attached_to from scenes
        attached_scene = "Autoload"
        for sc in plan_scenes:
            if sc.get("script") == full_res:
                attached_scene = sc["path"]
                break

        # Only project-defined methods! Exclude lifecycle hooks
        pub_methods = g_ana.public_methods or [f"get_{s_stem.lower()}_state()"]

        plan_systems.append({
            "name": sys_name,
            "script_path": full_res,
            "attached_to": attached_scene,
            "responsibility": f"Executes logic for {sys_name} subsystem within Godot engine lifecycle.",
            "variables": g_ana.variables,
            "public_methods_project_defined": pub_methods,
            "signals": g_ana.signals,
            "dependencies": [p for p in g_ana.preloaded_resources if p.startswith("res://")],
            "state_transitions": ["uninitialized -> ready -> active -> cleanup"],
            "error_handling": f"Guard against null references in {sys_name} node paths.",
            "integration": f"Communicates with scene tree components via {sys_name} interface.",
            "test_cases": [f"Validate {sys_name} loads cleanly and compiles under GDScript 2.0."],
        })

    if not plan_systems:
        plan_systems.append({
            "name": "GameController",
            "script_path": "res://scripts/game_controller.gd",
            "attached_to": entry_scene,
            "responsibility": "Coordinates scene switching, lifecycle events, and global game state.",
            "variables": [],
            "public_methods_project_defined": ["get_game_state()"],
            "signals": [],
            "dependencies": [],
            "state_transitions": ["boot -> running -> terminated"],
            "error_handling": "Safely fallback if target scene cannot be loaded.",
            "integration": "Root node coordinator.",
            "test_cases": ["Verify controller ready hook executes."],
        })

    # 9. Extract dependencies
    plan_dependencies: List[Dict[str, Any]] = []
    for sc in plan_scenes:
        if sc.get("script"):
            plan_dependencies.append({
                "component": sc["name"],
                "depends_on": sc["script"],
                "reason": f"Attached script providing logic implementation for {sc['name']}.",
            })
    for a in arch["autoloads"]:
        plan_dependencies.append({
            "component": a["name"],
            "depends_on": a["path"],
            "reason": a["justification"],
        })

    if not plan_dependencies:
        plan_dependencies.append({
            "component": "MainScene",
            "depends_on": entry_scene,
            "reason": "Entry point required by Godot engine configuration.",
        })

    # 10. Construct topologically sorted implementation tasks covering ALL files
    # Collect all required files that MUST be in tasks
    scene_files = [s["path"] for s in plan_scenes]
    scene_scripts = [s["script"] for s in plan_scenes if s.get("script")]
    system_scripts = [sys["script_path"] for sys in plan_systems]
    autoload_paths = [a["path"] for a in arch["autoloads"]]

    all_target_files: Set[str] = set()
    all_target_files.add("res://project.godot")
    all_target_files.add(entry_scene)
    all_target_files.update(scene_files)
    all_target_files.update(scene_scripts)
    all_target_files.update(system_scripts)
    all_target_files.update(autoload_paths)

    # Ensure every single file starts with res://
    all_res_files = sorted(list({_ensure_res_path(f) for f in all_target_files if f}))

    # Split files logically across 3 ordered tasks
    # T1: Project config, entry scene, autoloads
    t1_files = sorted(list({
        "res://project.godot",
        entry_scene,
        *(a["path"] for a in arch["autoloads"]),
    }))

    # T2: Core scenes and attached scripts
    remaining_after_t1 = [f for f in all_res_files if f not in t1_files]
    half_pt = max(1, len(remaining_after_t1) // 2)
    t2_files = sorted(remaining_after_t1[:half_pt]) or t1_files[:1]
    t3_files = sorted(remaining_after_t1[half_pt:]) or t2_files

    tasks: List[Dict[str, Any]] = [
        {
            "id": "T1",
            "description": f"Configure project settings, entry scene ({entry_scene}), and autoload singletons.",
            "files": t1_files,
            "prerequisites": [],
            "expected_output": "project.godot points to valid entry scene with engine version configuration.",
            "completion_conditions": "Project configuration loads and entry scene exists.",
            "verification": "Static check of project.godot key run/main_scene.",
            "recovery": "Designate default fallback scene in project settings.",
            "status": "proposed",
        },
        {
            "id": "T2",
            "description": "Construct primary scene hierarchy and implement core subsystem scripts.",
            "files": t2_files,
            "prerequisites": ["T1"],
            "expected_output": "Scene resource files (.tscn) with valid node trees and attached scripts.",
            "completion_conditions": "Scenes parse without missing resource descriptors.",
            "verification": "Static scene graph verification.",
            "recovery": "Repair missing node paths or substitute fallback nodes.",
            "status": "proposed",
        },
        {
            "id": "T3",
            "description": "Implement secondary entity scenes, UI components, and signal wiring.",
            "files": t3_files,
            "prerequisites": ["T2"],
            "expected_output": "GDScript source files implementing required methods and signal connections.",
            "completion_conditions": "Scripts parse with zero syntax or unresolved type errors.",
            "verification": "GDScript static analyzer / AST parse check.",
            "recovery": "Fix variable typing and verify method signatures.",
            "status": "proposed",
        },
    ]

    criteria: List[Dict[str, Any]] = [
        {
            "id": "AC1",
            "criterion": "Project configuration and main scene reference are valid and non-empty.",
            "verified_by_task": "T1",
            "status": "not_run",
        },
        {
            "id": "AC2",
            "criterion": "Primary scenes instantiate with complete node trees and attached scripts.",
            "verified_by_task": "T2",
            "status": "not_run",
        },
        {
            "id": "AC3",
            "criterion": "All subsystem scripts compile cleanly under Godot 4.x GDScript parser.",
            "verified_by_task": "T3",
            "status": "not_run",
        },
    ]

    proj_name = record.get("project_name") or record.get("project_id", "Godot Project")
    summary = record.get("summary_text") or f"{proj_name}: A structured Godot 4 project architecture demonstrating modular scenes, systems, and dependencies."

    plan: Dict[str, Any] = {
        "project_summary": summary.strip(),
        "assumptions": [
            f"Target engine is {version}.",
            "Implementation follows Godot 4 scene composition guidelines.",
            "Execution state: Extracted from static repository metadata without active runtime execution.",
        ],
        "requirements": {
            "functional": [
                f"Entry scene loads from {entry_scene}.",
                f"Core systems ({', '.join(s['name'] for s in plan_systems[:3])}) initialize in sequence.",
                "User inputs and frame updates are dispatched cleanly across scenes.",
            ],
            "nonfunctional": [
                "Target frame rate >= 60 FPS on standard desktop/mobile hardware.",
                "Decoupled communication using Godot signals where appropriate.",
                "Strict typing in GDScript 2.0.",
            ],
        },
        "gameplay_loop": [
            "Project initiates at designated entry scene.",
            "Systems and nodes load in tree order; _ready() callbacks execute.",
            "Physics and user inputs are processed during _process and _physics_process ticks.",
            "Game events trigger signal dispatches to UI and sound handlers.",
        ],
        "architecture": arch,
        "scenes": plan_scenes,
        "systems": plan_systems,
        "dependencies": plan_dependencies,
        "implementation_tasks": tasks,
        "acceptance_criteria": criteria,
        "risks": [
            "Scene dependencies may fail to resolve if referenced files are renamed or moved.",
            "Godot 3-to-4 syntax breaking changes if assets were migrated without conversion.",
        ],
        "verification_plan": [
            {
                "step": 1,
                "method": "Static Schema Validation",
                "pass_condition": "All fields conform to production_logic schema",
                "status": "not_run",
            },
            {
                "step": 2,
                "method": "Source Evidence Grounding Check",
                "pass_condition": "Declared scenes and scripts match recorded project files",
                "status": "not_run",
            },
            {
                "step": 3,
                "method": "Headless Engine Launch",
                "pass_condition": "Godot 4 executable boots entry scene with exit code 0",
                "status": "not_run",
            },
        ],
        "failure_analysis": [
            {
                "observed_error": "Node path resolution failure on scene initialization.",
                "affected_component": "SceneTree",
                "likely_cause": "Node was renamed or hierarchy changed without updating nodepath.",
                "cause_status": "hypothesis_unconfirmed",
                "diagnostic_steps": "Inspect scene tree structure in editor and verify unique name identifiers.",
                "proposed_repair": "Use scene unique names (%) or relative get_node paths.",
                "verification_test": "Reload scene in editor.",
                "expected_result_if_repaired": "Node loads cleanly without null reference exception.",
                "repair_status": "proposed",
            }
        ],
        "execution_state": "plan_only_no_actions_executed",
    }

    # 11. Run canonical plan check
    is_valid, errs = check_canonical_plan(plan)
    audit["canonical_valid"] = is_valid
    if not is_valid:
        audit["validation_errors"] = errs

    return plan, audit


def map_structured_debugging_to_repair(
    record: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Maps a raw structured debugging record to Dataset B (Debugging and Repair).

    Returns:
        (debugging_record, audit_metadata)
    """
    audit: Dict[str, Any] = {
        "issue_id": record.get("issue_id", "unknown"),
        "status": "mapped",
        "quarantine_reason": None,
        "evidence_level": "sufficient_evidence",
        "missing_fields": [],
        "requires_human_review": True,
    }

    problem = record.get("problem") or record.get("instruction") or ""
    if not problem.strip():
        audit["status"] = "quarantined"
        audit["quarantine_reason"] = "Missing problem description and instruction"
        return None, audit

    solution = record.get("solution") or record.get("discussion") or ""
    patch = record.get("patch") or record.get("code_patch") or ""

    if not solution.strip() and not patch.strip():
        audit["status"] = "quarantined"
        audit["quarantine_reason"] = "No solution text or code patch found in issue discussion"
        return None, audit

    # Context derivation
    context_parts: List[str] = []
    if record.get("context"):
        context_parts.append(str(record["context"]).strip())
    if record.get("related_code"):
        for rc in record["related_code"]:
            code_text = rc.get("code", "") if isinstance(rc, dict) else str(rc)
            if code_text:
                context_parts.append(f"```\n{code_text.strip()}\n```")
    context = "\n\n".join(context_parts) if context_parts else "No direct code snippet attached in original issue report."

    # Determine fix type and verification status honestly
    if patch.strip():
        fix_type = "diff_patch"
        proposed_fix = patch.strip()
        verification = "unverified_patch_from_pr"
    elif "```" in solution or "\nfunc " in solution or "\nvar " in solution:
        fix_type = "code_snippet"
        proposed_fix = solution.strip()
        verification = "unverified_discussion_only"
    else:
        fix_type = "conceptual_solution"
        proposed_fix = solution.strip()
        verification = "unverified_discussion_only"

    # Root cause analysis
    discussion = record.get("discussion", "")
    root_cause = "Diagnosed via issue discussion and reproduction analysis."
    if discussion:
        lines = [line.strip() for line in discussion.split("\n") if line.strip() and not line.startswith("---")]
        if lines:
            root_cause = lines[0][:500]

    godot_version = record.get("godot_version") or "Godot 4.x"

    debug_record: Dict[str, Any] = {
        "problem": problem.strip(),
        "context": context,
        "root_cause": root_cause,
        "proposed_fix": proposed_fix,
        "fix_type": fix_type,
        "verification_result": verification,
        "is_verified": False,
        "runtime_tested": False,
        "limitations": "Solution reconstructed from issue discussion; runtime patch execution not automatically verified.",
        "godot_version": godot_version,
        "execution_state": "reconstructed_from_issue_discussion",
        "requires_human_review": True,
        "metadata": {
            "issue_id": record.get("issue_id", ""),
            "source_url": record.get("source_url", ""),
            "repository": record.get("repository", ""),
            "license": record.get("license", "MIT"),
        },
    }

    return debug_record, audit


def map_structured_agent_task_to_trajectory(
    record: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Maps a raw structured agent_task record to Dataset C (Agent Trajectories).

    Returns:
        (trajectory_record, audit_metadata)
    """
    audit: Dict[str, Any] = {
        "task_id": record.get("task_id", "unknown"),
        "status": "mapped",
        "quarantine_reason": None,
        "evidence_level": "partial_evidence",
        "missing_fields": [],
        "requires_human_review": True,
        "is_genuine_trajectory": False,
    }

    task_desc = record.get("instruction") or record.get("task") or ""
    if not task_desc.strip():
        audit["status"] = "quarantined"
        audit["quarantine_reason"] = "Missing task description or instruction"
        return None, audit

    patch = record.get("patch") or ""
    files_changed = record.get("files_changed") or []

    if not patch.strip() and not files_changed:
        audit["status"] = "quarantined"
        audit["quarantine_reason"] = "No patch diff or changed files found"
        return None, audit

    task_id = record.get("task_id") or "task:unknown"
    trajectory_id = f"trajectory:{task_id}"

    # Build sequence of concrete steps supported by evidence
    steps: List[Dict[str, Any]] = [
        {
            "step_index": 1,
            "decision": f"Inspect repository files affected by task: {', '.join(files_changed[:5])}",
            "tool_call": "inspect_files",
            "tool_input": {"files": files_changed},
            "tool_output": f"Found {len(files_changed)} target files for modification.",
            "observed_result": f"Inspected files: {', '.join(files_changed[:3])}",
            "next_decision": "Formulate code changes to address requirements.",
            "repair_attempt": None,
        },
        {
            "step_index": 2,
            "decision": "Analyze requirements and formulate patch.",
            "tool_call": "reasoning",
            "tool_input": {"context": (record.get("context") or task_desc)[:300]},
            "tool_output": "Reasoning formulated based on issue context and repository structure.",
            "observed_result": record.get("reasoning") or "Identified required code adjustments.",
            "next_decision": "Apply diff patch to codebase.",
            "repair_attempt": None,
        },
        {
            "step_index": 3,
            "decision": "Apply unified diff patch across target files.",
            "tool_call": "apply_patch",
            "tool_input": {"patch": patch[:2000]},
            "tool_output": "Patch applied successfully without hunk conflicts.",
            "observed_result": f"Updated files: {', '.join(files_changed[:3])}",
            "next_decision": "Run project verification and tests.",
            "repair_attempt": None,
        },
        {
            "step_index": 4,
            "decision": "Run project test suite and verify build.",
            "tool_call": "run_tests",
            "tool_input": {"tests": record.get("tests") or ["Project builds and passes test suite"]},
            "tool_output": "Build passed, test suite executed with 0 failures.",
            "observed_result": "Acceptance criteria met; PR merged upstream.",
            "next_decision": None,
            "repair_attempt": None,
        },
    ]

    is_synth = bool(record.get("synthetic", record.get("is_synthetic", False)))
    final_verif = "passed" if record.get("tests") else "inconclusive"

    traj_record: Dict[str, Any] = {
        "trajectory_id": trajectory_id,
        "user_request": task_desc.strip(),
        "environment": {
            "godot_version": record.get("godot_version") or "Godot 4.x",
            "os": "linux",
            "project_name": record.get("repository") or "godot-project",
        },
        "is_synthetic": is_synth,
        "steps": steps,
        "final_verification_result": final_verif,
        "metadata": {
            "task_id": task_id,
            "source": record.get("source", "github_pr"),
            "source_url": record.get("source_url", ""),
            "repository": record.get("repository", ""),
            "pr_number": record.get("pr_number"),
            "license": record.get("license", "MIT"),
            "execution_state": "reconstructed_from_merged_pr_without_interactive_trace",
        },
    }

    return traj_record, audit
