#!/usr/bin/env python3
"""
Autonomous Godot AI Agent CLI Runner
====================================
CLI interface to inspect Godot projects, produce dependency-aware DAG plans,
stage code changes in isolated environments, validate with Godot 4 compiler,
perform bounded self-corrections, and persist resumable execution records.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from logic.orchestrator.models import ProjectPlan, TaskItem, TaskStatus
from logic.orchestrator.orchestrator import AutonomousProjectOrchestrator
from logic.orchestrator.project_analyzer import GodotProjectAnalyzer


def get_local_model_generator(use_adapter: bool = True):
    """Loads local Qwen model on GPU for inference if requested."""
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel

        base_id = "Qwen/Qwen2.5-Coder-7B-Instruct"
        adapter_path = REPO_ROOT / "godot-agent-lora" / "final_adapter"

        device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
        print(f"[*] Initializing model runtime on device: {device_name}")
        print(f"    - Base Model: {base_id} (bfloat16)")
        if use_adapter and adapter_path.exists():
            print(f"    - LoRA Adapter: {adapter_path} (Active)")
        elif not use_adapter:
            print("    - LoRA Adapter: None (Base Model Only requested)")
        else:
            print(f"    - LoRA Adapter: Not found at {adapter_path} (Using Base Model)")

        tok = AutoTokenizer.from_pretrained(base_id)
        model = AutoModelForCausalLM.from_pretrained(
            base_id,
            dtype=torch.bfloat16,
            device_map="auto" if torch.cuda.is_available() else None,
        )
        if use_adapter and adapter_path.exists():
            model = PeftModel.from_pretrained(model, str(adapter_path))
        model.eval()

        pad_id = tok.pad_token_id or tok.eos_token_id
        eos_id = tok.eos_token_id

        def _generator(messages: List[Dict[str, str]]) -> str:
            raw_inputs = tok.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            )
            device = getattr(model, "device", "cuda" if torch.cuda.is_available() else "cpu")
            inputs = {k: v.to(device) for k, v in raw_inputs.items()}
            input_len = inputs["input_ids"].shape[-1]
            with torch.inference_mode():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=1024,
                    do_sample=True,
                    temperature=0.3,
                    repetition_penalty=1.05,
                    pad_token_id=pad_id,
                    eos_token_id=eos_id,
                )
            new_toks = outputs[0, input_len:]
            return tok.decode(new_toks, skip_special_tokens=True).strip()

        return _generator
    except Exception as e:
        print(f"[!] Warning: Local GPU model could not be loaded: {e}. Falling back to deterministic mode.")
        return None


def format_status_badge(status: str) -> str:
    badges = {
        "passed": "\033[92m[PASSED]\033[0m",
        "failed": "\033[91m[FAILED]\033[0m",
        "blocked": "\033[93m[BLOCKED]\033[0m",
        "running": "\033[94m[RUNNING]\033[0m",
        "ready": "\033[96m[READY]\033[0m",
        "pending": "\033[90m[PENDING]\033[0m",
        "completed": "\033[92m[COMPLETED]\033[0m",
    }
    return badges.get(status.lower(), f"[{status.upper()}]")


def display_plan_summary(plan: ProjectPlan) -> None:
    print("\n" + "=" * 70)
    print(f"PLAN ID:       {plan.plan_id}")
    print(f"PROJECT PATH:  {plan.project_path}")
    print(f"USER REQUEST:  {plan.user_request}")
    print(f"COMPLEXITY:    {'Complex (Multi-Step DAG)' if plan.is_complex else 'Simple (Fast-Path)'}")
    print(f"OVERALL STATE: {format_status_badge(plan.status)}")
    print("=" * 70)
    print(f"{'TASK ID':<24} {'STATUS':<15} {'DEPS':<15} {'DESCRIPTION'}")
    print("-" * 70)
    for t in plan.tasks:
        deps_str = ",".join(t.dependencies) if t.dependencies else "-"
        print(f"{t.id:<24} {format_status_badge(t.status.value):<23} {deps_str:<15} {t.description[:40]}")
    print("=" * 70 + "\n")


def display_execution_report(summary: Dict[str, Any]) -> None:
    print("\n" + "=" * 70)
    print("FINAL EXECUTION REPORT")
    print("=" * 70)
    print(f"Overall Status: {format_status_badge(summary.get('overall_status', 'unknown'))}")
    print(
        f"Tasks: Total={summary.get('total_tasks', 0)} | "
        f"Passed={summary.get('passed_count', 0)} | "
        f"Failed={summary.get('failed_count', 0)} | "
        f"Blocked={summary.get('blocked_count', 0)}"
    )
    mod_files = summary.get("modified_files", [])
    print(f"Modified Files: {', '.join(mod_files) if mod_files else 'None'}")
    print("=" * 70)
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Autonomous Godot AI Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Plan and execute a request directly
  python3 scripts/autonomous_agent.py --project /path/to/game --request "Add double jump"

  # Plan only without touching project files
  python3 scripts/autonomous_agent.py --project /path/to/game --request "Add double jump" --plan-only

  # Execute a previously saved plan
  python3 scripts/autonomous_agent.py --project /path/to/game --execute

  # Resume an interrupted plan
  python3 scripts/autonomous_agent.py --project /path/to/game --resume

  # Check plan status
  python3 scripts/autonomous_agent.py --project /path/to/game --status
""",
    )
    parser.add_argument("--project", "-p", default="2d_platformer/platformer", help="Path to target Godot project")
    parser.add_argument("--request", "-r", type=str, help="Natural language request to plan and execute")
    parser.add_argument("--plan-only", action="store_true", help="Only generate and save the plan; do not execute")
    parser.add_argument("--execute", action="store_true", help="Execute planned tasks (uses existing plan if --request is omitted)")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted plan from .godot_agent/plan.json")
    parser.add_argument("--status", action="store_true", help="Show status of current plan")
    parser.add_argument("--max-repairs", type=int, default=2, help="Max compiler-driven repair attempts per task")
    parser.add_argument("--load-gpu-model", action="store_true", help="Load local 7B model onto GPU for inference")
    parser.add_argument("--base-model-only", action="store_true", help="Use base model without LoRA adapter")
    args = parser.parse_args()

    project_path = Path(args.project).resolve()
    if not project_path.exists() or not (project_path / "project.godot").exists():
        print(f"[!] Error: Invalid Godot project path: {project_path}")
        print("    The directory must exist and contain a valid 'project.godot' file.")
        sys.exit(1)

    print(f"[*] Target Godot 4 Project: {project_path}")
    analyzer = GodotProjectAnalyzer(project_path)
    meta = analyzer.get_project_metadata()
    features_display = meta.get("features") if meta.get("features") else "Default"
    print(f"[*] Engine Version: {meta.get('engine_version') or meta.get('version')}, Features: {features_display}")

    gen_fn = None
    if args.load_gpu_model:
        gen_fn = get_local_model_generator(use_adapter=not args.base_model_only)

    orchestrator = AutonomousProjectOrchestrator(project_path, generator_fn=gen_fn)

    # 1. Status query
    if args.status:
        plan = orchestrator.get_current_plan()
        if not plan:
            print(f"[*] No active plan found in {orchestrator.plan_file}")
            print("    Run with --request \"...\" (and optional --plan-only) to create a plan.")
        else:
            display_plan_summary(plan)
        return

    # 2. Resumption
    if args.resume:
        print("[*] Resuming execution from persisted plan...")
        plan = orchestrator.get_current_plan()
        if not plan:
            print(f"[!] Error: No existing plan found at {orchestrator.plan_file} to resume.")
            print("    Please provide --request \"...\" to create a new plan.")
            sys.exit(1)
        display_plan_summary(plan)
        summary = orchestrator.resume_execution(max_repairs_per_task=args.max_repairs)
        display_execution_report(summary)
        return

    # 3. Execute existing persisted plan (when --execute is given without --request)
    if args.execute and not args.request:
        print("[*] Executing persisted plan from disk...")
        plan = orchestrator.get_current_plan()
        if not plan:
            print(f"[!] Error: No persisted plan found at {orchestrator.plan_file}.")
            print("    Please provide --request \"...\" to create and execute a plan, or use --plan-only first.")
            sys.exit(1)
        display_plan_summary(plan)
        if plan.status == "completed" or all(t.status == TaskStatus.PASSED for t in plan.tasks):
            print("[*] All tasks in the plan are already passed. No pending work to execute.")
            summary = orchestrator.generate_execution_summary(plan, [])
            display_execution_report(summary)
            return
        summary = orchestrator.execute_plan(plan, max_repairs_per_task=args.max_repairs)
        display_execution_report(summary)
        return

    # 4. New Request (Plan-only or Plan-and-Execute)
    if args.request:
        print(f"[*] Analyzing project and generating plan for request: '{args.request}'...")
        plan = orchestrator.plan(args.request)
        display_plan_summary(plan)

        if args.plan_only:
            print(f"[*] Plan persisted to {orchestrator.plan_file}. Run with --execute or --resume to run tasks.")
            return

        # Default workflow: plan and execute
        print("[*] Executing plan in dependency order with staging and self-correction...")
        summary = orchestrator.execute_plan(plan, max_repairs_per_task=args.max_repairs)
        display_execution_report(summary)
        return

    # 5. No action specified: print actionable usage
    print("[!] Error: No action specified.")
    print("    Supported workflows:")
    print("      python3 scripts/autonomous_agent.py --project <path> --request \"...\" --plan-only")
    print("      python3 scripts/autonomous_agent.py --project <path> --execute")
    print("      python3 scripts/autonomous_agent.py --project <path> --request \"...\"")
    print("      python3 scripts/autonomous_agent.py --project <path> --resume")
    print("      python3 scripts/autonomous_agent.py --project <path> --status")
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
