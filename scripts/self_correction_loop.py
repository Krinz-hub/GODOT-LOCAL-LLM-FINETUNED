#!/usr/bin/env python3
"""
Bounded Self-Correction Execution Loop for Godot 4 AI Agent
============================================================
Implements a controlled staging and repair loop:
1. Validates action metadata and paths within workspace boundaries.
2. Stages changes in an isolated shadow project copy.
3. Runs Godot 4 compiler validation (--headless --check-only).
4. Catches actual compiler diagnostics and provides feedback to model.
5. Limits repair attempts (bounded loop).
6. Atomically applies changes only upon validation success; rolls back on failure.
"""

from __future__ import annotations

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

GODOT_BIN = (
    os.environ.get("GODOT_BIN")
    or (str(Path.home() / ".local" / "bin" / "godot4") if (Path.home() / ".local" / "bin" / "godot4").exists() else None)
    or "/home/piet/.local/bin/godot4"
)

# Explicit command allowlist for run_project action
ALLOWED_GODOT_FLAGS: List[str] = [
    "--headless",
    "--check-only",
    "--quit",
    "--quit-after",
    "--editor",
    "-s",
    "--script",
    "--path",
]


@dataclass
class ValidationReport:
    is_valid: bool
    exit_code: int
    diagnostics: str
    stdout: str
    stderr: str


@dataclass
class SelfCorrectionResult:
    success: bool
    total_attempts: int
    final_action: Optional[Dict[str, Any]]
    file_written: Optional[str]
    diagnostics: List[str]
    elapsed_sec: float
    error: Optional[str] = None


def sanitize_relative_path(base_dir: Path, rel_path: str) -> Path:
    """Ensures file paths strictly resolve inside project boundaries."""
    if not rel_path or not rel_path.strip():
        raise ValueError("File path cannot be empty")
    cleaned = rel_path.strip().lstrip("/")
    target = (base_dir / cleaned).resolve()
    if not str(target).startswith(str(base_dir.resolve())):
        raise PermissionError(f"Security: Target path '{rel_path}' escapes workspace '{base_dir}'")
    return target


def parse_action_with_delimiters(text: str) -> Dict[str, Any]:
    """Parses actions supporting both JSON and <godot_action> delimited blocks."""
    cleaned = text.strip()

    # 1. Delimited <godot_action> block
    delim_match = re.search(r"<godot_action>(.*?)</godot_action>", cleaned, re.DOTALL | re.IGNORECASE)
    if delim_match:
        action_json_str = delim_match.group(1).strip()
        try:
            data = json.loads(action_json_str)
            if isinstance(data, dict):
                # Check for adjoining unescaped GDScript or TSCN code blocks
                code_match = re.search(r"```(?:gdscript|tscn)?\s*\n(.*?)```", cleaned, re.DOTALL)
                if code_match and "parameters" in data:
                    params = data.setdefault("parameters", {})
                    if not params.get("content"):
                        params["content"] = code_match.group(1).strip()
                return data
        except Exception:
            pass

    # 2. Standard JSON block enclosed in markdown or raw
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    json_candidate = fence_match.group(1).strip() if fence_match else ""
    if not json_candidate:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_candidate = cleaned[start : end + 1]

    if json_candidate:
        try:
            data = json.loads(json_candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            try:
                data = json.loads(json_candidate, strict=False)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

    # 3. Fallback extraction of code block if action_type is inferred
    code_match = re.search(r"```(?:gdscript)?\s*\n(.*?)```", cleaned, re.DOTALL)
    if code_match:
        return {
            "thought": "Inferred script creation from markdown code block",
            "action_type": "create_or_update_script",
            "parameters": {
                "file_path": "script.gd",
                "content": code_match.group(1).strip(),
            },
        }

    return {
        "thought": "Failed to parse structured action from output",
        "action_type": "chat_response",
        "parameters": {"message": cleaned},
    }


def validate_script_in_context(project_dir: Path, script_rel_path: str, code: str) -> ValidationReport:
    """Validates GDScript using Godot 4 headless compiler inside project context."""
    if not GODOT_BIN or not Path(GODOT_BIN).exists():
        return ValidationReport(False, -1, f"Godot binary not found at {GODOT_BIN}", "", "")

    target_file = project_dir / script_rel_path
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(code, encoding="utf-8")

    cmd = [
        GODOT_BIN,
        "--headless",
        "--check-only",
        "--path",
        str(project_dir),
        "-s",
        str(target_file),
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = (res.stderr or res.stdout).strip()
        # Clean standard engine header
        clean_diag = re.sub(r"Godot Engine v[^\n]+\n?", "", output).strip()

        is_valid = (res.returncode == 0) and ("Parse Error" not in clean_diag)
        return ValidationReport(
            is_valid=is_valid,
            exit_code=res.returncode,
            diagnostics=clean_diag,
            stdout=res.stdout,
            stderr=res.stderr,
        )
    except subprocess.TimeoutExpired:
        return ValidationReport(False, -2, "Godot validation timed out (>10s)", "", "Timeout")
    except Exception as e:
        return ValidationReport(False, -3, f"Execution error: {e}", "", str(e))


def run_bounded_self_correction(
    project_path: Path,
    prompt: str,
    generator_fn: Callable[[List[Dict[str, str]]], str],
    max_repair_attempts: int = 2,
    timeout_sec: float = 30.0,
) -> SelfCorrectionResult:
    """Executes proposed actions with isolated staging and bounded self-correction."""
    t0 = time.time()
    diagnostics: List[str] = []
    
    if not project_path.exists():
        return SelfCorrectionResult(
            success=False,
            total_attempts=0,
            final_action=None,
            file_written=None,
            diagnostics=["Project path does not exist"],
            elapsed_sec=0.0,
            error=f"Project path '{project_path}' not found",
        )

    # Initial generation
    conversation: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are an autonomous Godot 4 developer. Plan and generate actions matching GodotAgentAction.\n"
                "You may format your action as JSON or using <godot_action>...</godot_action> followed by ```gdscript."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    attempt = 0
    final_action: Optional[Dict[str, Any]] = None

    while attempt <= max_repair_attempts:
        attempt += 1
        raw_output = generator_fn(conversation)
        action = parse_action_with_delimiters(raw_output)
        final_action = action
        action_type = action.get("action_type")
        params = action.get("parameters", {})

        # Handle non-file actions directly
        if action_type in ("read_file", "list_project_files", "chat_response"):
            return SelfCorrectionResult(
                success=True,
                total_attempts=attempt,
                final_action=action,
                file_written=None,
                diagnostics=[],
                elapsed_sec=round(time.time() - t0, 2),
            )

        if action_type not in ("create_or_update_script", "create_scene", "edit_scene"):
            diagnostics.append(f"Unrecognized action_type '{action_type}'")
            break

        rel_path = params.get("file_path", "")
        content = params.get("content", "")

        try:
            target_path = sanitize_relative_path(project_path, rel_path)
        except (ValueError, PermissionError) as e:
            diagnostics.append(f"Path security violation: {e}")
            break

        # Stage change in temporary shadow directory
        with tempfile.TemporaryDirectory(prefix="godot_shadow_") as shadow_dir:
            shadow_path = Path(shadow_dir)
            
            # Copy project.godot to simulate project context
            proj_godot = project_path / "project.godot"
            if proj_godot.exists():
                shutil.copy2(proj_godot, shadow_path / "project.godot")
            else:
                (shadow_path / "project.godot").write_text("config_version=5\n[application]\nconfig/name=\"Shadow\"\n")

            # Validate GDScript if it's a script action
            if rel_path.endswith(".gd"):
                val_report = validate_script_in_context(shadow_path, rel_path, content)
                
                if val_report.is_valid:
                    # VALIDATION PASSED: Atomically write to actual project
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_text(content, encoding="utf-8")
                    return SelfCorrectionResult(
                        success=True,
                        total_attempts=attempt,
                        final_action=action,
                        file_written=rel_path,
                        diagnostics=diagnostics,
                        elapsed_sec=round(time.time() - t0, 2),
                    )
                else:
                    diag_msg = val_report.diagnostics or "Compiler parse error"
                    diagnostics.append(f"Attempt {attempt} validation failure: {diag_msg}")

                    if attempt > max_repair_attempts:
                        break

                    # Provide compiler feedback for repair attempt
                    conversation.append({"role": "assistant", "content": raw_output})
                    repair_prompt = (
                        f"Your GDScript code for '{rel_path}' failed Godot 4 compilation with diagnostics:\n"
                        f"{diag_msg}\n\n"
                        f"Please fix the error. Return the corrected complete code."
                    )
                    conversation.append({"role": "user", "content": repair_prompt})
            else:
                # Non-script files (e.g. .tscn) - write directly if basic header check passes
                if rel_path.endswith(".tscn") and not content.strip().startswith("[gd_scene"):
                    diagnostics.append(f"Attempt {attempt}: Invalid TSCN format (missing [gd_scene])")
                    if attempt > max_repair_attempts:
                        break
                    conversation.append({"role": "assistant", "content": raw_output})
                    conversation.append({"role": "user", "content": "The .tscn file must begin with [gd_scene. Fix it."})
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_text(content, encoding="utf-8")
                    return SelfCorrectionResult(
                        success=True,
                        total_attempts=attempt,
                        final_action=action,
                        file_written=rel_path,
                        diagnostics=diagnostics,
                        elapsed_sec=round(time.time() - t0, 2),
                    )

    # All attempts failed or unrecoverable error
    return SelfCorrectionResult(
        success=False,
        total_attempts=attempt,
        final_action=final_action,
        file_written=None,
        diagnostics=diagnostics,
        elapsed_sec=round(time.time() - t0, 2),
        error="Validation checks failed across all bounded repair attempts. Project state preserved.",
    )
