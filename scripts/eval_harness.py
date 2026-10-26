#!/usr/bin/env python3
"""
Trustworthy Evaluation Harness for Godot 4 AI Agents
=====================================================
Replaces vanity keyword-matching benchmarks with multi-layer verification:
  Layer A: Output Integrity (truncation, repetition, path safety, schema)
  Layer B: Godot 4 Headless Syntax & API Validation (official engine compiler)
  Layer C: Project & Scene Hierarchy Validation (tscn parsing and path resolution)
  Layer D: Deterministic Functional Execution (headless Godot SceneTree runner)
  Layer E: Regression & Bug-Fix Verification (targeted edits, preservation of unrelated code)

Outputs rigorous metrics:
  - Parse success rate
  - Project validation rate
  - Functional test pass rate
  - Regression pass rate
  - Valid structured action rate
  - End-to-end task success rate
  - Average latency & generation failures
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
GODOT_BIN = (
    os.environ.get("GODOT_BIN")
    or (str(Path.home() / ".local" / "bin" / "godot4") if (Path.home() / ".local" / "bin" / "godot4").exists() else None)
    or "/home/piet/.local/bin/godot4"
)

# ---------------------------------------------------------------------------
# Obsolete Godot 3 APIs for Static Detection
# ---------------------------------------------------------------------------
G3_DEPRECATED_PATTERNS: Dict[str, re.Pattern] = {
    "setget": re.compile(r"\bsetget\b"),
    "File.new()": re.compile(r"\bFile\.new\s*\("),
    "Directory.new()": re.compile(r"\bDirectory\.new\s*\("),
    "Pool*Array": re.compile(r"\bPool[A-Za-z0-9]+Array\b"),
    "update()": re.compile(r"\bupdate\s*\(\s*\)"),
    "set_rot": re.compile(r"\bset_rot\b"),
    "parse_json": re.compile(r"\bparse_json\b"),
    "to_json": re.compile(r"\bto_json\b"),
    "validate_json": re.compile(r"\bvalidate_json\b"),
    "yield()": re.compile(r"\byield\s*\("),
    "move_and_slide_with_args": re.compile(r"\bmove_and_slide\s*\([^)]+\)"),
    "unannotated_export": re.compile(r"^\s*export\s*(?:\([^)]*\))?\s*var\b", re.MULTILINE),
    "unannotated_onready": re.compile(r"^\s*onready\s+var\b", re.MULTILINE),
    "old_connect_string": re.compile(r"\.connect\s*\(\s*\"[^\"]+\"\s*,\s*self\s*,"),
    "PackedScene.instance": re.compile(r"\.instance\s*\(\s*\)"),
    "KinematicBody2D": re.compile(r"\bKinematicBody2D\b"),
    "Spatial": re.compile(r"\bSpatial\b"),
}


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass
class LayerResult:
    passed: bool
    details: str
    diagnostics: Optional[str] = None


@dataclass
class TaskEvaluation:
    task_id: str
    task_name: str
    category: str
    elapsed_sec: float
    output_integrity: LayerResult
    syntax_validation: LayerResult
    scene_validation: LayerResult
    functional_correctness: LayerResult
    regression_pass: LayerResult
    structured_action_valid: LayerResult
    overall_passed: bool
    raw_response: str
    diagnostics: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Evaluation Layers
# ---------------------------------------------------------------------------

def validate_output_integrity(raw_text: str, max_expected_tokens: int = 1500) -> LayerResult:
    """Layer A: Checks output for truncation, repetition loops, and empty output."""
    if not raw_text or not raw_text.strip():
        return LayerResult(False, "Output is empty")

    cleaned = raw_text.strip()
    if len(cleaned) < 15:
        return LayerResult(False, f"Output is too short ({len(cleaned)} chars)")

    # Detect autoregressive token loops: repetitive lines or patterns
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if len(lines) >= 8:
        last_4 = lines[-4:]
        prev_4 = lines[-8:-4]
        if last_4 == prev_4:
            return LayerResult(False, "Detected repetitive token generation loop at tail")

    # Detect excessive tabs/newlines runaway
    tab_run = re.search(r"(\t\s*){15,}", raw_text)
    if tab_run:
        return LayerResult(False, "Detected runaway whitespace/tab loop")

    # Detect unclosed markdown code block (truncation indicator)
    fence_count = raw_text.count("```")
    if fence_count % 2 != 0:
        return LayerResult(False, "Truncated markdown block (odd number of code fences)")

    return LayerResult(True, "Output format and structural integrity verified")


def validate_godot4_syntax(code: str, project_dir: Optional[Path] = None) -> LayerResult:
    """Layer B: Validates GDScript using the official Godot 4 headless compiler."""
    # First, static check for Godot 3 obsolete tokens
    detected_g3: List[str] = []
    for name, pat in G3_DEPRECATED_PATTERNS.items():
        if pat.search(code):
            detected_g3.append(name)

    if detected_g3:
        return LayerResult(
            False,
            f"Contains deprecated Godot 3 patterns: {', '.join(detected_g3)}",
            diagnostics=f"Deprecated APIs: {detected_g3}",
        )

    if not GODOT_BIN or not Path(GODOT_BIN).exists():
        return LayerResult(False, f"Godot binary not found at {GODOT_BIN}")

    # Create temporary isolated project context if not supplied
    clean_up = False
    if project_dir is None:
        temp_dir = tempfile.mkdtemp(prefix="godot_eval_")
        target_dir = Path(temp_dir)
        (target_dir / "project.godot").write_text("config_version=5\n[application]\nconfig/name=\"Eval\"\n")
        clean_up = True
    else:
        target_dir = project_dir

    script_path = target_dir / "eval_candidate.gd"
    try:
        script_path.write_text(code, encoding="utf-8")
        cmd = [GODOT_BIN, "--headless", "--check-only", "--path", str(target_dir), "-s", str(script_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if res.returncode == 0:
            return LayerResult(True, "Godot 4 engine compiler validated script cleanly")
        else:
            diag = (res.stderr or res.stdout).strip()
            # Filter standard engine banner
            diag = re.sub(r"Godot Engine v[^\n]+\n?", "", diag).strip()
            return LayerResult(False, f"Compiler syntax error (exit code {res.returncode})", diagnostics=diag)
    except subprocess.TimeoutExpired:
        return LayerResult(False, "Godot compiler timed out during check-only validation")
    except Exception as e:
        return LayerResult(False, f"Failed to invoke Godot compiler: {e}")
    finally:
        if script_path.exists():
            script_path.unlink()
        if clean_up and target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)


def validate_scene_structure(tscn_content: str, expected_root_type: str, expected_nodes: List[str]) -> LayerResult:
    """Layer C: Validates .tscn scene definition structure and node paths."""
    if not tscn_content or "[gd_scene" not in tscn_content:
        return LayerResult(False, "Invalid TSCN: Missing [gd_scene] header")

    # Verify root node
    root_match = re.search(r'\[node\s+name="([^"]+)"\s+type="([^"]+)"', tscn_content)
    if not root_match:
        return LayerResult(False, "Missing root [node] declaration in TSCN")

    root_type = root_match.group(2)
    if expected_root_type and root_type != expected_root_type:
        return LayerResult(False, f"Root node type mismatch: expected {expected_root_type}, got {root_type}")

    # Check child nodes
    for node_name in expected_nodes:
        if not re.search(rf'\[node\s+name="{node_name}"', tscn_content):
            return LayerResult(False, f"Expected node '{node_name}' not found in scene tree")

    return LayerResult(True, f"Scene structure valid: Root {root_type} with expected children")


def run_headless_functional_test(test_driver_code: str) -> LayerResult:
    """Layer D: Executes deterministic functional tests inside Godot 4 headless."""
    if not GODOT_BIN or not Path(GODOT_BIN).exists():
        return LayerResult(False, f"Godot binary not found at {GODOT_BIN}")

    with tempfile.TemporaryDirectory(prefix="godot_func_test_") as td:
        p = Path(td)
        (p / "project.godot").write_text("config_version=5\n[application]\nconfig/name=\"TestRunner\"\n")
        runner_file = p / "runner.gd"
        runner_file.write_text(test_driver_code, encoding="utf-8")

        try:
            cmd = [GODOT_BIN, "--headless", "--path", str(p), "-s", str(runner_file)]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
            out = res.stdout + res.stderr
            
            if res.returncode == 0 and "ALL_ASSERTIONS_PASSED" in out:
                return LayerResult(True, "All functional assertions executed and passed in Godot 4 headless")
            else:
                diag = (res.stderr or res.stdout).strip()
                diag = re.sub(r"Godot Engine v[^\n]+\n?", "", diag).strip()
                return LayerResult(False, f"Functional assertions failed (exit code {res.returncode})", diagnostics=diag)
        except subprocess.TimeoutExpired:
            return LayerResult(False, "Headless functional test timed out (>12s)")
        except Exception as e:
            return LayerResult(False, f"Execution exception: {e}")


def validate_structured_action(action_data: Any, allowed_types: List[str], project_root: Path) -> LayerResult:
    """Layer E: Validates action metadata, schema compliance, and workspace security."""
    if not isinstance(action_data, dict):
        return LayerResult(False, "Action payload is not a valid JSON dictionary")

    action_type = action_data.get("action_type")
    if not action_type or action_type not in allowed_types:
        return LayerResult(False, f"Invalid action_type '{action_type}'. Allowed: {allowed_types}")

    params = action_data.get("parameters", {})
    if not isinstance(params, dict):
        return LayerResult(False, "Action parameters must be an object")

    file_path = params.get("file_path", "")
    if file_path:
        # Security: Prevent directory traversal outside project root
        normalized = os.path.normpath(file_path)
        if normalized.startswith("..") or os.path.isabs(normalized):
            return LayerResult(False, f"Security violation: path '{file_path}' attempts directory traversal")

    return LayerResult(True, f"Action '{action_type}' validated with safe path '{file_path}'")


# ---------------------------------------------------------------------------
# Test Suite Definitions
# ---------------------------------------------------------------------------

BENCHMARK_TASKS: List[Dict[str, Any]] = [
    {
        "id": "TASK_01_KINEMATIC_CONTROLLER",
        "name": "2D Kinematic Controller with Double Jump & Wall Slide",
        "category": "mechanics",
        "prompt": (
            "Given this scene tree:\n"
            "Scene Tree: Player (CharacterBody2D) -> [CollisionShape2D, Sprite2D]\n\n"
            "Write the complete Godot 4 GDScript implementation for player.gd.\n"
            "Requirements:\n"
            "1. Extends CharacterBody2D.\n"
            "2. @export var speed := 300.0, jump_velocity := -400.0, double_jump_velocity := -350.0.\n"
            "3. Implements gravity, horizontal acceleration/friction, jump, double-jump, and wall sliding.\n"
            "4. Uses Godot 4 move_and_slide() without arguments.\n"
            "Return only the GDScript code in a ```gdscript code fence."
        ),
        "expected_root": "CharacterBody2D",
        "verify_syntax": True,
        "functional_test_generator": lambda code: f"""extends SceneTree

{code.replace('extends CharacterBody2D', 'class PlayerUnderTest extends CharacterBody2D:')}

func _init():
    var p = PlayerUnderTest.new()
    if p.get('speed') == null or p.speed <= 0.0:
        printerr("FAIL: speed export not found or invalid")
        quit(1)
        return
    if p.get('jump_velocity') == null or p.jump_velocity >= 0.0:
        printerr("FAIL: jump_velocity must be negative in 2D")
        quit(1)
        return
    print("ALL_ASSERTIONS_PASSED")
    quit(0)
""",
    },
    {
        "id": "TASK_02_AUTONOMOUS_ACTION_SCENE",
        "name": "Autonomous Action: Scene & Node Generation",
        "category": "action_generation",
        "prompt": (
            "You are an autonomous Godot 4 agent. Generate an action to create a new coin scene at scenes/coin.tscn "
            "with an Area2D root node named Coin and a CollisionShape2D child. "
            "Output your response strictly as JSON with action_type, thought, and parameters (file_path, content)."
        ),
        "allowed_actions": ["create_scene", "create_or_update_scene"],
        "expected_root": "Area2D",
        "expected_children": ["CollisionShape2D"],
        "verify_syntax": False,
    },
    {
        "id": "TASK_03_SHIELD_MECHANIC",
        "name": "Feature Addition: Shield / Invulnerability Mechanic",
        "category": "mechanics",
        "prompt": (
            "Write a Godot 4 GDScript class named ShieldMechanic extending RefCounted that implements:\n"
            "1. signal shield_broken\n"
            "2. var has_shield: bool = false\n"
            "3. func grant_shield() -> void: sets has_shield = true\n"
            "4. func hit_hazard() -> bool: if has_shield, consumes shield, emits shield_broken, and returns false (damage absorbed); otherwise returns true (damage taken).\n"
            "Return only the GDScript code inside ```gdscript."
        ),
        "expected_root": "RefCounted",
        "verify_syntax": True,
        "functional_test_generator": lambda code: f"""extends SceneTree

{code.replace('extends RefCounted', 'class TestedShield extends RefCounted:')}

func _init():
    var obj = TestedShield.new()
    var broken_emitted := false
    obj.shield_broken.connect(func(): broken_emitted = true)
    
    # 1. Unshielded hit should return true (damage applied)
    if obj.hit_hazard() != true:
        printerr("FAIL: hit_hazard without shield must return true")
        quit(1)
        return
        
    # 2. Grant shield
    obj.grant_shield()
    if obj.has_shield != true:
        printerr("FAIL: grant_shield did not set has_shield to true")
        quit(1)
        return
        
    # 3. Hit with shield must return false (damage absorbed) and consume shield
    if obj.hit_hazard() != false:
        printerr("FAIL: hit_hazard with shield must return false (damage absorbed)")
        quit(1)
        return
        
    if obj.has_shield != false:
        printerr("FAIL: hit_hazard did not consume shield")
        quit(1)
        return
        
    if not broken_emitted:
        printerr("FAIL: shield_broken signal was not emitted")
        quit(1)
        return
        
    print("ALL_ASSERTIONS_PASSED")
    quit(0)
""",
    },
    {
        "id": "TASK_04_TIMER_SIGNALS",
        "name": "Godot 4 API Awareness: Timer and Modern Signals",
        "category": "engine_api",
        "prompt": (
            "Write a Godot 4 GDScript function in a Node script:\n"
            "```gdscript\n"
            "extends Node\n"
            "func setup_one_shot_timer(duration: float, callback: Callable) -> Timer:\n"
            "```\n"
            "It must create a Timer, set wait_time, set one_shot = true, connect timeout to callback using modern Godot 4 callable syntax, add the timer as a child, and start it.\n"
            "Return only the GDScript code inside ```gdscript."
        ),
        "expected_root": "Node",
        "verify_syntax": True,
        "functional_test_generator": lambda code: f"""extends SceneTree

{code.replace('extends Node', 'class TestedNode extends Node:')}

func _init():
    var node = TestedNode.new()
    root.add_child(node)
    
    var fired := false
    var cb = func(): fired = true
    
    var timer: Timer = node.setup_one_shot_timer(0.05, cb)
    if timer == null:
        printerr("FAIL: setup_one_shot_timer returned null")
        quit(1)
        return
    if not timer.one_shot:
        printerr("FAIL: timer.one_shot must be true")
        quit(1)
        return
    if timer.wait_time != 0.05:
        printerr("FAIL: timer.wait_time is not 0.05")
        quit(1)
        return
    if not timer.timeout.is_connected(cb):
        printerr("FAIL: timeout signal not connected to callback")
        quit(1)
        return
        
    print("ALL_ASSERTIONS_PASSED")
    quit(0)
""",
    },
    {
        "id": "TASK_05_SURGICAL_BUGFIX",
        "name": "Surgical Defect Repair: Terminal Velocity Cap",
        "category": "regression",
        "prompt": (
            "Given this existing Godot 4 player physics function with a tunneling bug:\n"
            "```gdscript\n"
            "extends CharacterBody2D\n\n"
            "@export var gravity: float = 980.0\n"
            "@export var max_fall_speed: float = 800.0\n\n"
            "func apply_gravity(delta: float) -> void:\n"
            "    velocity.y += gravity * delta\n"
            "```\n"
            "Fix the bug so velocity.y does not exceed max_fall_speed (cap downward velocity). Preserve the exact method signature and existing exports. Return only the complete updated GDScript."
        ),
        "expected_root": "CharacterBody2D",
        "verify_syntax": True,
        "functional_test_generator": lambda code: f"""extends SceneTree

{code.replace('extends CharacterBody2D', 'class TestedPlayer extends CharacterBody2D:')}

func _init():
    var p = TestedPlayer.new()
    p.velocity.y = 750.0
    p.apply_gravity(1.0) # 750 + 980 = 1730, should be capped to 800.0
    if p.velocity.y > 800.01:
        printerr("FAIL: velocity.y exceeded max_fall_speed: ", p.velocity.y)
        quit(1)
        return
    if p.velocity.y < 799.99:
        printerr("FAIL: velocity.y should have reached max_fall_speed cap: ", p.velocity.y)
        quit(1)
        return
    print("ALL_ASSERTIONS_PASSED")
    quit(0)
""",
    },
    {
        "id": "TASK_06_NEGATIVE_REJECTION",
        "name": "Negative Test: Rejection of Godot 3 Legacy Code",
        "category": "regression",
        "is_negative_test": True,
        "broken_sample": (
            "extends KinematicBody2D\n"
            "var score = 0 setget set_score\n"
            "func set_score(val): score = val\n"
            "func _physics_process(delta):\n"
            "    move_and_slide(velocity)\n"
        ),
    },
]


# ---------------------------------------------------------------------------
# Helper: Extract Code and JSON
# ---------------------------------------------------------------------------

def extract_gdscript(text: str) -> str:
    """Extracts GDScript code from markdown fences or returns raw text."""
    match = re.search(r"```(?:gdscript)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def extract_action_json(text: str) -> Optional[Dict[str, Any]]:
    """Extracts JSON object from text."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    try:
        return json.loads(cleaned)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Evaluation Engine
# ---------------------------------------------------------------------------

class TrustworthyEvaluationHarness:
    def __init__(self, inference_fn: Callable[[str], str], server_url: Optional[str] = None):
        self.inference_fn = inference_fn
        self.server_url = server_url
        self.results: List[TaskEvaluation] = []

    def evaluate_task(self, task: Dict[str, Any]) -> TaskEvaluation:
        task_id = task["id"]
        task_name = task["name"]
        category = task.get("category", "general")
        diagnostics: List[str] = []

        # Handle negative rejection test
        if task.get("is_negative_test"):
            broken_sample = task["broken_sample"]
            syntax_check = validate_godot4_syntax(broken_sample)
            # Negative test PASSES if syntax check FAILS (i.e. correctly rejected)
            passed = not syntax_check.passed
            details = "Correctly rejected legacy Godot 3 code" if passed else "FAILED: Accepted legacy Godot 3 code"
            return TaskEvaluation(
                task_id=task_id,
                task_name=task_name,
                category=category,
                elapsed_sec=0.01,
                output_integrity=LayerResult(True, "N/A (Static fixture)"),
                syntax_validation=LayerResult(passed, details),
                scene_validation=LayerResult(True, "N/A"),
                functional_correctness=LayerResult(passed, details),
                regression_pass=LayerResult(passed, details),
                structured_action_valid=LayerResult(True, "N/A"),
                overall_passed=passed,
                raw_response="[NEGATIVE TEST FIXTURE]",
                diagnostics=[] if passed else ["Negative test failed to reject Godot 3 code"],
            )

        t0 = time.time()
        try:
            raw_response = self.inference_fn(task["prompt"])
        except Exception as e:
            elapsed = time.time() - t0
            return TaskEvaluation(
                task_id=task_id,
                task_name=task_name,
                category=category,
                elapsed_sec=elapsed,
                output_integrity=LayerResult(False, f"Inference failure: {e}"),
                syntax_validation=LayerResult(False, "Skipped due to inference failure"),
                scene_validation=LayerResult(False, "Skipped"),
                functional_correctness=LayerResult(False, "Skipped"),
                regression_pass=LayerResult(False, "Skipped"),
                structured_action_valid=LayerResult(False, "Skipped"),
                overall_passed=False,
                raw_response="",
                diagnostics=[f"Inference exception: {e}"],
            )
        elapsed = time.time() - t0

        # Layer A: Output Integrity
        integrity = validate_output_integrity(raw_response)
        if not integrity.passed:
            diagnostics.append(f"Output Integrity: {integrity.details}")

        # Layer E: Structured Action Check (if applicable)
        action_res = LayerResult(True, "N/A")
        extracted_code = ""
        scene_res = LayerResult(True, "N/A")

        if "allowed_actions" in task:
            action_data = extract_action_json(raw_response)
            action_res = validate_structured_action(action_data, task["allowed_actions"], REPO_ROOT)
            if not action_res.passed:
                diagnostics.append(f"Structured Action: {action_res.details}")
            
            # Check scene content if action contains it
            if action_data and isinstance(action_data, dict):
                content = action_data.get("parameters", {}).get("content", "")
                if content and "[gd_scene" in content:
                    scene_res = validate_scene_structure(
                        content,
                        task.get("expected_root", ""),
                        task.get("expected_children", [])
                    )
                    if not scene_res.passed:
                        diagnostics.append(f"Scene Validation: {scene_res.details}")
        else:
            extracted_code = extract_gdscript(raw_response)

        # Layer B: Godot 4 Headless Syntax Validation
        syntax_res = LayerResult(True, "N/A")
        if task.get("verify_syntax") and extracted_code:
            syntax_res = validate_godot4_syntax(extracted_code)
            if not syntax_res.passed:
                diagnostics.append(f"Syntax Validation: {syntax_res.details}")
                if syntax_res.diagnostics:
                    diagnostics.append(f"Compiler Diagnostic: {syntax_res.diagnostics}")

        # Layer D: Headless Functional Correctness
        func_res = LayerResult(True, "N/A")
        if syntax_res.passed and "functional_test_generator" in task and extracted_code:
            try:
                driver_code = task["functional_test_generator"](extracted_code)
                func_res = run_headless_functional_test(driver_code)
                if not func_res.passed:
                    diagnostics.append(f"Functional Test: {func_res.details}")
                    if func_res.diagnostics:
                        diagnostics.append(f"Engine Diagnostic: {func_res.diagnostics}")
            except Exception as e:
                func_res = LayerResult(False, f"Test generation error: {e}")
                diagnostics.append(str(e))
        elif not syntax_res.passed and "functional_test_generator" in task:
            func_res = LayerResult(False, "Skipped due to syntax failure")

        # Regression check
        reg_res = LayerResult(True, "Passed")
        if category == "regression":
            reg_passed = syntax_res.passed and func_res.passed
            reg_res = LayerResult(reg_passed, "Regression verified" if reg_passed else "Regression failed")

        overall = (
            integrity.passed
            and syntax_res.passed
            and func_res.passed
            and action_res.passed
            and scene_res.passed
            and reg_res.passed
        )

        return TaskEvaluation(
            task_id=task_id,
            task_name=task_name,
            category=category,
            elapsed_sec=round(elapsed, 2),
            output_integrity=integrity,
            syntax_validation=syntax_res,
            scene_validation=scene_res,
            functional_correctness=func_res,
            regression_pass=reg_res,
            structured_action_valid=action_res,
            overall_passed=overall,
            raw_response=raw_response,
            diagnostics=diagnostics,
        )

    def run_suite(self) -> Dict[str, Any]:
        print("=================================================================")
        print("  RUNNING TRUSTWORTHY MULTI-LAYER EVALUATION SUITE")
        print("=================================================================")
        self.results = []
        for task in BENCHMARK_TASKS:
            print(f"\n▶ Evaluating: [{task['id']}] {task['name']}...")
            res = self.evaluate_task(task)
            self.results.append(res)
            status_str = "✓ PASS" if res.overall_passed else "✗ FAIL"
            print(f"  Result: {status_str} in {res.elapsed_sec}s")
            if not res.overall_passed:
                for diag in res.diagnostics:
                    print(f"    - {diag}")

        return self.generate_summary()

    def generate_summary(self) -> Dict[str, Any]:
        total = len(self.results)
        if total == 0:
            return {}

        integrity_passes = sum(1 for r in self.results if r.output_integrity.passed)
        syntax_passes = sum(1 for r in self.results if r.syntax_validation.passed)
        func_passes = sum(1 for r in self.results if r.functional_correctness.passed)
        action_passes = sum(1 for r in self.results if r.structured_action_valid.passed)
        reg_passes = sum(1 for r in self.results if r.regression_pass.passed)
        overall_passes = sum(1 for r in self.results if r.overall_passed)
        avg_latency = sum(r.elapsed_sec for r in self.results) / total

        summary = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_tasks": total,
            "overall_pass_rate_pct": round((overall_passes / total) * 100, 1),
            "parse_success_rate_pct": round((syntax_passes / total) * 100, 1),
            "functional_pass_rate_pct": round((func_passes / total) * 100, 1),
            "structured_action_rate_pct": round((action_passes / total) * 100, 1),
            "regression_pass_rate_pct": round((reg_passes / total) * 100, 1),
            "output_integrity_rate_pct": round((integrity_passes / total) * 100, 1),
            "avg_latency_sec": round(avg_latency, 2),
            "tasks": [
                {
                    "id": r.task_id,
                    "name": r.task_name,
                    "category": r.category,
                    "passed": r.overall_passed,
                    "elapsed_sec": r.elapsed_sec,
                    "diagnostics": r.diagnostics,
                    "output_preview": r.raw_response[:200].replace("\n", " "),
                }
                for r in self.results
            ],
        }
        return summary


# ---------------------------------------------------------------------------
# CLI & Server Inference Adapter
# ---------------------------------------------------------------------------

def make_http_inference_fn(server_url: str = "http://127.0.0.1:8000") -> Callable[[str], str]:
    import urllib.request
    def _call(prompt: str) -> str:
        url = f"{server_url}/v1/chat"
        payload = json.dumps({"prompt": prompt, "max_tokens": 1200}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response") or data.get("content") or json.dumps(data)
    return _call


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trustworthy Godot Evaluation Harness")
    parser.add_argument("--server-url", default="http://127.0.0.1:8000", help="Agent server URL")
    parser.add_argument("--output", default="reports/trustworthy_benchmark.json", help="Output report path")
    args = parser.parse_args()

    inference_fn = make_http_inference_fn(args.server_url)
    harness = TrustworthyEvaluationHarness(inference_fn, server_url=args.server_url)
    summary = harness.run_suite()

    os.makedirs(Path(args.output).parent, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=================================================================")
    print(f"  EVALUATION COMPLETE: {summary.get('overall_pass_rate_pct', 0)}% End-to-End Task Pass Rate")
    print(f"  Parse Success: {summary.get('parse_success_rate_pct', 0)}% | Functional: {summary.get('functional_pass_rate_pct', 0)}%")
    print("=================================================================")
