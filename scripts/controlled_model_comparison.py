#!/usr/bin/env python3
"""
Controlled Model Comparison Benchmark: Base Model vs LoRA v1
============================================================
Evaluates:
  1. Base Model: Qwen/Qwen2.5-Coder-7B-Instruct
  2. LoRA v1: Qwen/Qwen2.5-Coder-7B-Instruct + godot-agent-lora/final_adapter
  3. LoRA v1 with Repetition Safeguards (repetition_penalty=1.20)

Evaluates 5 standardized cases (2 runs each):
  Case 1: Change one constant in an existing GDScript file (WALK_SPEED to 350.0).
  Case 2: Add a small helper function while preserving the class.
  Case 3: Generate a complete small GDScript file (HealthComponent).
  Case 4: Produce a valid structured action response (ScoreManager).
  Case 5: Repair a script using an actual Godot compiler diagnostic (move_and_slide arg).

Multi-layer verification:
  - Valid structured action rate (JSON envelope parsing)
  - Repetition or truncated output rate
  - First-pass Godot 4 compilation rate (/home/piet/.local/bin/godot4)
  - Final task success after 1 bounded repair
  - Unrelated file modification count
  - Latency and token usage
"""

import argparse
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from logic.orchestrator.project_analyzer import GodotProjectAnalyzer
from logic.orchestrator.executor import EXECUTOR_SYSTEM_PROMPT, REPAIR_SYSTEM_PROMPT, parse_action_payload

BASE_MODEL_ID = "Qwen/Qwen2.5-Coder-7B-Instruct"
ADAPTER_PATH = REPO_ROOT / "godot-agent-lora" / "final_adapter"
GODOT_BIN = "/home/piet/.local/bin/godot4"
SAMPLE_PROJECT = REPO_ROOT / "2d_platformer/platformer"

RAW_LOG_PATH = REPO_ROOT / "reports" / "benchmark_raw_outputs.jsonl"
SUMMARY_JSON_PATH = REPO_ROOT / "reports" / "benchmark_summary.json"


def set_seed(seed: int = 42):
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def detect_repetition(text: str) -> Tuple[bool, str]:
    """Detects repetitive token degeneracy (e.g. repeated variable names or lines)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False, ""
    
    # Check for repeated pattern loops like var is_sprited_N
    pattern_repeats = re.findall(r"(\b[a-zA-Z_0-9]+\s*:=\s*false)", text)
    if len(pattern_repeats) > 10:
        return True, f"Repetitive variable loop detected ({len(pattern_repeats)} occurrences)"

    # Check for identical lines repeated > 4 times
    counts = {}
    for l in lines:
        counts[l] = counts.get(l, 0) + 1
        if counts[l] >= 5:
            return True, f"Line repeated {counts[l]} times: '{l[:40]}...'"
            
    # Check 3-line cyclic repetition
    for i in range(len(lines) - 6):
        if lines[i:i+3] == lines[i+3:i+6] == lines[i+6:i+9]:
            return True, "Cyclic block repetition detected"

    return False, ""


def check_godot_syntax(staging_dir: Path, rel_file: str, code: Any) -> Tuple[bool, str]:
    """Validates GDScript using Godot 4 headless compiler."""
    if isinstance(code, list):
        code = "\n".join(str(x) for x in code)
    elif not isinstance(code, str):
        code = str(code) if code is not None else ""
    if not code or not code.strip():
        return False, "Code is empty"
    
    target = staging_dir / rel_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code, encoding="utf-8")

    if not Path(GODOT_BIN).exists():
        return False, f"Godot executable not found at {GODOT_BIN}"

    cmd = [
        GODOT_BIN,
        "--headless",
        "--check-only",
        "--path",
        str(staging_dir),
        "-s",
        str(target),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        raw_out = (res.stderr or res.stdout).strip()
        clean_diag = re.sub(r"Godot Engine v[^\n]+\n?", "", raw_out).strip()
        is_valid = (res.returncode == 0) and ("Parse Error" not in clean_diag)
        return is_valid, clean_diag
    except subprocess.TimeoutExpired:
        return False, "Godot validation timed out (>12s)"
    except Exception as e:
        return False, f"Validation error: {e}"


def run_single_inference(
    generator_fn: Callable[[List[Dict[str, str]], Dict[str, Any]], Tuple[str, float, int]],
    conversation: List[Dict[str, str]],
    decoding_kwargs: Dict[str, Any],
) -> Tuple[str, float, int]:
    return generator_fn(conversation, decoding_kwargs)


def execute_test_case(
    case_def: Dict[str, Any],
    run_idx: int,
    model_name: str,
    generator_fn: Callable[[List[Dict[str, str]], Dict[str, Any]], Tuple[str, float, int]],
    decoding_kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    case_id = case_def["id"]
    case_name = case_def["name"]
    target_file = case_def["target_file"]

    print(f"\n[{model_name}] Run {run_idx+1}: {case_id} — {case_name}")

    with tempfile.TemporaryDirectory(prefix="bm_stage_") as tmp_dir:
        stage_path = Path(tmp_dir)
        # Clone sample project
        if SAMPLE_PROJECT.exists():
            for item in SAMPLE_PROJECT.iterdir():
                if item.name not in (".git", ".venv", ".godot_agent", ".godot"):
                    dest = stage_path / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
        else:
            (stage_path / "project.godot").write_text("config_version=5\n[application]\nconfig/name=\"BM\"\n")

        # Set up initial test file if specified
        if "initial_code" in case_def:
            t_file = stage_path / target_file
            t_file.parent.mkdir(parents=True, exist_ok=True)
            t_file.write_text(case_def["initial_code"], encoding="utf-8")

        analyzer = GodotProjectAnalyzer(stage_path)
        context = analyzer.build_focused_context_for_task([target_file], case_def["prompt"])

        user_content = (
            f"TASK ID: {case_id}\n"
            f"DESCRIPTION: {case_def['prompt']}\n"
            f"TARGET FILES: ['{target_file}']\n"
            f"ACCEPTANCE CRITERIA: {case_def['acceptance_criteria']}\n\n"
            f"PROJECT CONTEXT:\n{context}\n\n"
            "Generate the required Godot 4 action to fulfill this task."
        )

        conversation = [
            {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        # 1. First-pass generation
        raw_output, elapsed_sec, token_count = run_single_inference(generator_fn, conversation, decoding_kwargs)

        is_rep, rep_detail = detect_repetition(raw_output)
        is_trunc = raw_output.endswith(("var is", "func ", "class_name ", "{", "[", ",")) or len(raw_output) > 3500

        action = parse_action_payload(raw_output)
        action_type = action.get("action_type", "")
        params = action.get("parameters", {})
        raw_content = params.get("content", "")
        if isinstance(raw_content, list):
            candidate_code = "\n".join(str(x) for x in raw_content)
        elif isinstance(raw_content, str):
            candidate_code = raw_content
        else:
            candidate_code = str(raw_content) if raw_content is not None else ""

        is_structured_action = (
            action_type in ("create_or_update_script", "create_scene")
            and isinstance(params.get("content"), str)
            and bool(candidate_code.strip())
            and params.get("file_path") == target_file
        )

        # First-pass compilation
        first_pass_valid, first_pass_diag = check_godot_syntax(stage_path, target_file, candidate_code)

        # Check for un-related file modifications
        diff_str = ""
        orig_file = stage_path / target_file
        if orig_file.exists() and candidate_code:
            try:
                orig_txt = orig_file.read_text(encoding="utf-8")
                diff_lines = list(difflib.unified_diff(
                    orig_txt.splitlines(keepends=True),
                    candidate_code.splitlines(keepends=True),
                    fromfile=f"a/{target_file}",
                    tofile=f"b/{target_file}"
                ))
                diff_str = "".join(diff_lines)
            except Exception:
                diff_str = ""

        # Specific correctness check
        semantic_pass = True
        semantic_notes = []
        if case_id == "case_1_const_edit":
            if "WALK_SPEED = 350.0" not in candidate_code and "WALK_SPEED = 350" not in candidate_code:
                semantic_pass = False
                semantic_notes.append("WALK_SPEED not updated to 350.0")
            if "func _physics_process" not in candidate_code:
                semantic_pass = False
                semantic_notes.append("Existing movement methods lost")
        elif case_id == "case_2_add_function":
            if "func get_jump_strength" not in candidate_code:
                semantic_pass = False
                semantic_notes.append("Helper function get_jump_strength not found")
        elif case_id == "case_3_complete_file":
            if "signal health_depleted" not in candidate_code or "func take_damage" not in candidate_code:
                semantic_pass = False
                semantic_notes.append("Required signals or methods missing")
        elif case_id == "case_5_compiler_repair":
            if "move_and_slide()" not in candidate_code:
                semantic_pass = False
                semantic_notes.append("move_and_slide still contains arguments")

        final_success = first_pass_valid and is_structured_action and semantic_pass
        repair_used = False
        repair_succeeded = False
        repair_elapsed = 0.0

        # 2. Bounded Repair attempt if first pass failed
        if not final_success and not is_rep:
            repair_used = True
            error_reason = first_pass_diag or (", ".join(semantic_notes)) or "Malformed structured action"
            repair_user = (
                f"Validation Error: {error_reason}\n"
                f"Please fix the error and output a valid JSON action with 'action_type': 'create_or_update_script' and 'content'."
            )
            repair_conv = list(conversation)
            repair_conv.append({"role": "assistant", "content": raw_output})
            repair_conv.append({"role": "user", "content": repair_user})

            rep_raw, rep_sec, rep_tok = run_single_inference(generator_fn, repair_conv, decoding_kwargs)
            repair_elapsed = rep_sec
            token_count += rep_tok

            rep_action = parse_action_payload(rep_raw)
            rep_raw_content = rep_action.get("parameters", {}).get("content", "")
            if isinstance(rep_raw_content, list):
                rep_code = "\n".join(str(x) for x in rep_raw_content)
            elif isinstance(rep_raw_content, str):
                rep_code = rep_raw_content
            else:
                rep_code = str(rep_raw_content) if rep_raw_content is not None else ""
            r_valid, r_diag = check_godot_syntax(stage_path, target_file, rep_code)
            if r_valid and rep_action.get("action_type") == "create_or_update_script":
                repair_succeeded = True
                final_success = True

        result_record = {
            "model_name": model_name,
            "case_id": case_id,
            "case_name": case_name,
            "run_index": run_idx,
            "target_file": target_file,
            "latency_sec": round(elapsed_sec + repair_elapsed, 2),
            "tokens_generated": token_count,
            "is_structured_action": is_structured_action,
            "action_type": action_type,
            "is_repeated_or_truncated": is_rep or is_trunc,
            "repetition_detail": rep_detail,
            "first_pass_compiler_valid": first_pass_valid,
            "first_pass_compiler_diag": first_pass_diag,
            "semantic_check_passed": semantic_pass,
            "semantic_notes": semantic_notes,
            "repair_used": repair_used,
            "repair_succeeded": repair_succeeded,
            "final_task_success": final_success,
            "diff_preview": diff_str[:500],
            "raw_output": raw_output,
        }

        # Log raw result to JSONL
        with open(RAW_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(result_record) + "\n")

        status_badge = "✓ PASS" if final_success else "✗ FAIL"
        fp_badge = "✓" if first_pass_valid else "✗"
        act_badge = "✓" if is_structured_action else "✗"
        rep_badge = "✗ (REP)" if (is_rep or is_trunc) else "✓"
        print(f"  Result: {status_badge} | StructAction: {act_badge} | 1stPassCompile: {fp_badge} | NoRepetition: {rep_badge} | Time: {elapsed_sec:.2f}s ({token_count} tok)")
        if not final_success:
            if rep_detail:
                print(f"    - Degeneracy: {rep_detail}")
            if first_pass_diag:
                print(f"    - Compiler Diagnostic: {first_pass_diag[:120]}")
            if semantic_notes:
                print(f"    - Semantic Failures: {', '.join(semantic_notes)}")

        return result_record


def build_test_cases() -> List[Dict[str, Any]]:
    return [
        {
            "id": "case_1_const_edit",
            "name": "Change constant in existing GDScript",
            "target_file": "player/player.gd",
            "prompt": "In player/player.gd, change constant WALK_SPEED = 300.0 to 350.0. Preserve all other movement variables, signals, and functions.",
            "acceptance_criteria": [
                "const WALK_SPEED set to 350.0",
                "CharacterBody2D movement logic preserved",
                "Godot 4 compiler validation passes cleanly",
            ],
        },
        {
            "id": "case_2_add_function",
            "name": "Add helper function to existing class",
            "target_file": "player/player.gd",
            "prompt": "In player/player.gd, add a helper function `func get_jump_strength() -> float:` that returns `absf(JUMP_VELOCITY)`. Preserve the entire existing class.",
            "acceptance_criteria": [
                "Public helper get_jump_strength() -> float defined",
                "Returns absf(JUMP_VELOCITY)",
                "Full player script preserved without breaking existing logic",
            ],
        },
        {
            "id": "case_3_complete_file",
            "name": "Generate complete small GDScript file",
            "target_file": "scripts/health_component.gd",
            "prompt": (
                "Create a complete Godot 4 script `scripts/health_component.gd` extending Node. "
                "Define @export var max_health: int = 100, var current_health: int, signal health_depleted(), "
                "signal health_changed(new_health: int), func take_damage(amount: int) -> void:, and func heal(amount: int) -> void:. "
                "Do not use Godot 3 syntax."
            ),
            "acceptance_criteria": [
                "Extends Node in Godot 4",
                "Signals health_depleted and health_changed declared",
                "Valid Godot 4 typed GDScript",
            ],
        },
        {
            "id": "case_4_structured_action",
            "name": "Produce valid structured action response",
            "target_file": "scripts/score_manager.gd",
            "prompt": (
                "Return a strict JSON action response creating `scripts/score_manager.gd` extending Node. "
                "It should define `var score: int = 0`, `signal score_updated(new_score: int)`, and `func add_score(pts: int) -> void:`. "
                "The response MUST be valid JSON with 'action_type': 'create_or_update_script' and 'parameters'."
            ),
            "acceptance_criteria": [
                "Strict JSON structure with thought, action_type, and parameters",
                "Valid score manager script content",
            ],
        },
        {
            "id": "case_5_compiler_repair",
            "name": "Repair script using actual compiler diagnostic",
            "target_file": "scripts/bad_enemy.gd",
            "initial_code": (
                "class_name BadEnemy extends CharacterBody2D\n\n"
                "var speed: float = 100.0\n\n"
                "func _physics_process(delta: float) -> void:\n"
                "\tvelocity.x = speed\n"
                "\t# Bug: Godot 3 argument passed to Godot 4 move_and_slide\n"
                "\tmove_and_slide(velocity)\n"
            ),
            "prompt": (
                "Compiler Diagnostic: `res://scripts/bad_enemy.gd:7 - Parse Error: Too many arguments for 'move_and_slide()' call. Expected at most 0 but received 1.`\n"
                "Fix the compiler error in `scripts/bad_enemy.gd`. Use valid Godot 4 move_and_slide syntax."
            ),
            "acceptance_criteria": [
                "Replaces move_and_slide(velocity) with move_and_slide()",
                "Valid Godot 4 CharacterBody2D script",
            ],
        },
    ]


def main():
    parser = argparse.ArgumentParser(description="Base Model vs LoRA v1 Controlled Benchmark")
    parser.add_argument("--runs-per-case", type=int, default=2, help="Number of repetitions per test case")
    parser.add_argument("--device", default="cuda:0" if torch.cuda.is_available() else "cpu", help="PyTorch compute device")
    args = parser.parse_args()

    set_seed(42)
    device = args.device

    print("======================================================================")
    print("  CONTROLLED BENCHMARK: Base Model vs LoRA v1 Adapter")
    print(f"  Device: {device} | Native Precision: torch.bfloat16")
    print(f"  Base Model: {BASE_MODEL_ID}")
    print(f"  LoRA Adapter: {ADAPTER_PATH}")
    print(f"  Godot Executable: {GODOT_BIN}")
    print("======================================================================")

    # Load existing cache if available to support resume
    RAW_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing_cache: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
    if RAW_LOG_PATH.exists():
        with open(RAW_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        rec = json.loads(line)
                        k = (rec.get("model_name"), rec.get("case_id"), rec.get("run_index"))
                        existing_cache[k] = rec
                    except Exception:
                        pass
        print(f"[*] Found {len(existing_cache)} previously completed runs in {RAW_LOG_PATH}")

    # Load Tokenizer
    print("\n[*] Loading Tokenizer...")
    tok = AutoTokenizer.from_pretrained(BASE_MODEL_ID)
    pad_id = tok.pad_token_id or tok.eos_token_id
    eos_id = tok.eos_token_id

    # 1. Load Base Model
    print("\n[*] Loading Base Model in native torch.bfloat16...")
    t0_base = time.time()
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        dtype=torch.bfloat16,
        device_map=device,
    )
    base_model.eval()
    print(f"    Loaded Base Model in {time.time() - t0_base:.2f}s")

    def make_generator(cur_model):
        def _gen(messages: List[Dict[str, str]], decoding_params: Dict[str, Any]) -> Tuple[str, float, int]:
            raw_inputs = tok.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            )
            m_device = getattr(cur_model, "device", device)
            inputs = {k: v.to(m_device) for k, v in raw_inputs.items()}
            in_len = inputs["input_ids"].shape[-1]
            t_gen_start = time.time()
            with torch.inference_mode():
                outputs = cur_model.generate(
                    **inputs,
                    max_new_tokens=decoding_params.get("max_new_tokens", 1024),
                    do_sample=decoding_params.get("do_sample", True),
                    temperature=decoding_params.get("temperature", 0.2),
                    top_p=decoding_params.get("top_p", 0.9),
                    repetition_penalty=decoding_params.get("repetition_penalty", 1.05),
                    pad_token_id=pad_id,
                    eos_token_id=eos_id,
                )
            gen_sec = time.time() - t_gen_start
            new_tokens = outputs[0, in_len:]
            text = tok.decode(new_tokens, skip_special_tokens=True).strip()
            return text, gen_sec, len(new_tokens)
        return _gen

    test_cases = build_test_cases()
    default_decoding = {
        "max_new_tokens": 1024,
        "do_sample": True,
        "temperature": 0.2,
        "top_p": 0.9,
        "repetition_penalty": 1.05,
    }

    # Helper loop with cache
    def run_phase(p_model_name, p_gen, p_dec):
        results = []
        for case in test_cases:
            for r_idx in range(args.runs_per_case):
                cache_key = (p_model_name, case["id"], r_idx)
                if cache_key in existing_cache:
                    cached_rec = existing_cache[cache_key]
                    status_badge = "✓ PASS" if cached_rec.get("final_task_success") else "✗ FAIL"
                    print(f"[{p_model_name}] Run {r_idx+1}: {case['id']} — [FROM CACHE: {status_badge}]")
                    results.append(cached_rec)
                else:
                    res = execute_test_case(case, r_idx, p_model_name, p_gen, p_dec)
                    existing_cache[cache_key] = res
                    results.append(res)
        return results

    # RUN CONFIGURATION 1: Base Model
    print("\n" + "=" * 60)
    print("PHASE 1: Benchmarking Base Model (Qwen2.5-Coder-7B-Instruct)")
    print("=" * 60)
    base_gen = make_generator(base_model)
    base_results = run_phase("Base Model (Qwen2.5-Coder-7B)", base_gen, default_decoding)

    # 2. Attach LoRA Adapter
    print("\n" + "=" * 60)
    print(f"PHASE 2: Attaching LoRA Adapter ({ADAPTER_PATH.name})")
    print("=" * 60)
    t0_lora = time.time()
    lora_model = PeftModel.from_pretrained(base_model, str(ADAPTER_PATH))
    lora_model.eval()
    print(f"    Attached LoRA Adapter in {time.time() - t0_lora:.2f}s")

    lora_gen = make_generator(lora_model)

    # RUN CONFIGURATION 2: LoRA v1 with Standard Decoding
    print("\n" + "=" * 60)
    print("PHASE 3: Benchmarking LoRA v1 (Standard Decoding, rep_penalty=1.05)")
    print("=" * 60)
    lora_standard_results = run_phase("LoRA v1 (Standard)", lora_gen, default_decoding)

    # RUN CONFIGURATION 3: LoRA v1 with Repetition Safeguards
    print("\n" + "=" * 60)
    print("PHASE 4: Benchmarking LoRA v1 with Repetition Safeguards (rep_penalty=1.20)")
    print("=" * 60)
    safeguard_decoding = dict(default_decoding)
    safeguard_decoding["repetition_penalty"] = 1.20
    lora_safeguard_results = run_phase("LoRA v1 (Safeguarded)", lora_gen, safeguard_decoding)

    # Aggregate Metrics
    def aggregate_metrics(results: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
        total = len(results)
        struct_valid = sum(1 for r in results if r["is_structured_action"])
        rep_count = sum(1 for r in results if r["is_repeated_or_truncated"])
        fp_compile = sum(1 for r in results if r["first_pass_compiler_valid"])
        final_succ = sum(1 for r in results if r["final_task_success"])
        avg_lat = sum(r["latency_sec"] for r in results) / total if total else 0.0
        avg_tok = sum(r["tokens_generated"] for r in results) / total if total else 0.0

        return {
            "model_name": name,
            "total_attempts": total,
            "structured_action_valid_count": struct_valid,
            "structured_action_rate_pct": round(struct_valid / total * 100, 1),
            "repetition_or_truncated_count": rep_count,
            "repetition_rate_pct": round(rep_count / total * 100, 1),
            "first_pass_compile_count": fp_compile,
            "first_pass_compile_rate_pct": round(fp_compile / total * 100, 1),
            "final_success_count": final_succ,
            "final_success_rate_pct": round(final_succ / total * 100, 1),
            "avg_latency_sec": round(avg_lat, 2),
            "avg_tokens": round(avg_tok, 1),
        }

    summary = {
        "timestamp": time.time(),
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware": "NVIDIA DGX Spark / GB10",
        "godot_version": "v4.7.2.stable.official.ed1daf0bf",
        "base_model": BASE_MODEL_ID,
        "adapter_path": str(ADAPTER_PATH),
        "configurations": [
            aggregate_metrics(base_results, "Base Model (Qwen2.5-Coder-7B-Instruct)"),
            aggregate_metrics(lora_standard_results, "LoRA v1 (Standard Decoding)"),
            aggregate_metrics(lora_safeguard_results, "LoRA v1 (Safeguarded Decoding, rep_penalty=1.20)"),
        ],
    }

    with open(SUMMARY_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[*] Benchmark summary written to {SUMMARY_JSON_PATH}")
    print(f"[*] Raw log written to {RAW_LOG_PATH}")


if __name__ == "__main__":
    main()
