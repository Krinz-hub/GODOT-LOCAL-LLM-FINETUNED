"""Export cleaned and structured records into training format for Qwen2.5-Coder."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from logic_pipeline.logging_config import get_logger

logger = get_logger("processing.export")

DEFAULT_SYSTEM_PROMPT = "You are an expert Godot 4 Engine developer and autonomous AI agent."
LOGIC_SYSTEM_PROMPT = (
    "You are a Godot game-production planning agent. Produce coherent, "
    "dependency-aware, testable game plans. Distinguish assumptions, proposed "
    "actions, and verified results."
)


def format_sharegpt_record(
    user_prompt: str,
    assistant_response: str,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> Dict[str, Any]:
    """Builds standard 3-message ShareGPT/ChatML format."""
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": assistant_response},
        ]
    }


def export_production_logic_to_sharegpt(
    plan: Dict[str, Any],
    user_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """Exports production logic plan where assistant message is a JSON string of schema keys."""
    prompt = user_prompt or f"Create a production-ready Godot 4 architecture and implementation plan for: {plan.get('project_summary', 'a Godot game')}"
    plan_json = json.dumps(plan, ensure_ascii=False)
    return format_sharegpt_record(
        user_prompt=prompt,
        assistant_response=plan_json,
        system_prompt=LOGIC_SYSTEM_PROMPT,
    )


def export_scene_script_to_sharegpt(
    filename: str,
    scene_tree_summary: str,
    gdscript_code: str,
) -> Dict[str, Any]:
    """Exports scene-grounded script implementation record."""
    user_prompt = f"Given this scene tree:\n{scene_tree_summary}\n\nWrite the GDScript implementation for {filename}."
    assistant_content = f"```gdscript\n{gdscript_code.strip()}\n```"
    return format_sharegpt_record(
        user_prompt=user_prompt,
        assistant_response=assistant_content,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
    )


def export_debugging_to_sharegpt(
    error_description: str,
    source_context: str,
    patch: str,
    explanation: str,
) -> Dict[str, Any]:
    """Exports a debugging and repair instruction example."""
    user_prompt = (
        f"Diagnose and fix the following Godot issue:\n"
        f"Observed Error: {error_description}\n\n"
        f"Context:\n{source_context}"
    )
    assistant_content = (
        f"### Root Cause Analysis\n{explanation}\n\n"
        f"### Proposed Patch\n```diff\n{patch.strip()}\n```"
    )
    return format_sharegpt_record(
        user_prompt=user_prompt,
        assistant_response=assistant_content,
        system_prompt="You are an expert Godot 4 Engine developer specializing in debugging and repair.",
    )


def export_to_sharegpt(
    records: List[Dict[str, Any]],
    output_path: Path,
) -> int:
    """Writes formatted records to JSONL file on disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            count += 1
    logger.info("Exported %d records to %s", count, output_path)
    return count


def export_dataset_a_to_sharegpt(
    ingested_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Converts Dataset A ingested production plans into ShareGPT format."""
    sharegpt_records = []
    for item in ingested_records:
        plan = item.get("plan") or item
        proj_id = item.get("project_id") or plan.get("project_summary", "project")
        user_prompt = f"Create a production-ready Godot 4 architecture and implementation plan for: {plan.get('project_summary', proj_id)}"
        rec = format_sharegpt_record(
            user_prompt=user_prompt,
            assistant_response=json.dumps(plan, ensure_ascii=False),
            system_prompt=LOGIC_SYSTEM_PROMPT,
        )
        rec["project_id"] = proj_id
        rec["dataset_type"] = "dataset_a_production_logic"
        sharegpt_records.append(rec)
    return sharegpt_records


def export_dataset_a_architecture_to_sharegpt(
    ingested_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Converts Dataset A records into pure Architecture planning format."""
    sharegpt_records = []
    arch_system_prompt = (
        "You are an expert Godot 4 architect. Given high-level requirements, "
        "design the scene structure, autoloads, core systems, and dependencies."
    )
    for item in ingested_records:
        plan = item.get("plan") or item
        proj_id = item.get("project_id") or plan.get("project_summary", "project")
        user_prompt = f"Design the project architecture, scene hierarchy, systems, and dependencies for the Godot game: {plan.get('project_summary', proj_id)}"
        arch_data = {
            "project_summary": plan.get("project_summary"),
            "architecture": plan.get("architecture"),
            "scenes": plan.get("scenes"),
            "systems": plan.get("systems"),
            "dependencies": plan.get("dependencies"),
        }
        rec = format_sharegpt_record(
            user_prompt=user_prompt,
            assistant_response=json.dumps(arch_data, ensure_ascii=False),
            system_prompt=arch_system_prompt,
        )
        rec["project_id"] = proj_id
        rec["dataset_type"] = "dataset_a_architecture"
        sharegpt_records.append(rec)
    return sharegpt_records


def export_dataset_b_to_sharegpt(
    ingested_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Converts Dataset B ingested debugging records into ShareGPT format."""
    sharegpt_records = []
    system_prompt = "You are an expert Godot 4 Engine developer specializing in debugging and repair."
    for item in ingested_records:
        rec = item.get("record") or item
        issue_id = item.get("issue_id") or rec.get("problem", "issue")
        meta = rec.get("metadata", {})
        repo = meta.get("repository", "godot-project")

        user_prompt = (
            f"Diagnose and resolve the following Godot issue:\n"
            f"Observed Problem:\n{rec.get('problem', '')}\n\n"
            f"Context:\n{rec.get('context', 'None provided')}"
        )
        assistant_content = (
            f"### Root Cause Analysis\n{rec.get('root_cause', 'Diagnosed via issue context.')}\n\n"
            f"### Proposed Fix ({rec.get('fix_type', 'solution')})\n{rec.get('proposed_fix', '')}\n\n"
            f"### Verification & Limitations\n{rec.get('limitations', 'Reconstructed from issue discussion.')}"
        )
        sg_rec = format_sharegpt_record(
            user_prompt=user_prompt,
            assistant_response=assistant_content,
            system_prompt=system_prompt,
        )
        sg_rec["repository"] = repo
        sg_rec["issue_id"] = issue_id
        sg_rec["dataset_type"] = "dataset_b_debugging"
        sharegpt_records.append(sg_rec)
    return sharegpt_records


def export_dataset_c_to_sharegpt(
    ingested_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Converts Dataset C ingested agent trajectories into ShareGPT format."""
    sharegpt_records = []
    system_prompt = (
        "You are an autonomous Godot development agent capable of executing multi-step "
        "tool interactions to inspect, edit, and verify game projects."
    )
    for item in ingested_records:
        traj = item.get("record") or item
        traj_id = traj.get("trajectory_id", "traj")
        meta = traj.get("metadata", {})
        repo = meta.get("repository", "godot-project")

        # Build trajectory transcript
        transcript_lines = [
            f"### Autonomous Trajectory: {traj_id}",
            f"Environment: Godot {traj.get('environment', {}).get('godot_version', '4.x')} on {traj.get('environment', {}).get('os', 'linux')}",
            "",
        ]
        for step in traj.get("steps", []):
            transcript_lines.append(f"**Step {step['step_index']}: {step['decision']}**")
            transcript_lines.append(f"Tool Call: `{step['tool_call']}`")
            transcript_lines.append(f"Observation: {step['observed_result']}")
            transcript_lines.append("")

        transcript_lines.append(f"Final Verification Result: {traj.get('final_verification_result', 'passed')}")

        sg_rec = format_sharegpt_record(
            user_prompt=traj.get("user_request", "Perform task"),
            assistant_response="\n".join(transcript_lines),
            system_prompt=system_prompt,
        )
        sg_rec["repository"] = repo
        sg_rec["trajectory_id"] = traj_id
        sg_rec["dataset_type"] = "dataset_c_trajectories"
        sharegpt_records.append(sg_rec)
    return sharegpt_records

