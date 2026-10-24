#!/usr/bin/env python3
"""Auditor Client for Godot AI Model.

Submits implementation and correction prompts to the fine-tuned Godot AI model
running on http://127.0.0.1:8000, retrieves model-generated code, applies changes
to the target Godot project, and logs prompt experiments.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
from typing import Any, Dict, List, Optional

SERVER_URL = "http://127.0.0.1:8000"
DEFAULT_PROJECT = "/home/piet/Documents/godot/zombies"
EXP_JSONL = Path("/home/piet/Documents/dataset/reports/prompt_experiments.jsonl")


def query_model_chat(prompt: str, max_tokens: int = 1500, temperature: float = 0.2) -> str:
    """Queries the model via the /v1/chat endpoint (matching native fine-tuning format)."""
    payload = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        f"{SERVER_URL}/v1/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("response", "")


def query_model_action(prompt: str, project_path: str = DEFAULT_PROJECT) -> Dict[str, Any]:
    """Queries the model via /v1/act for structured actions."""
    payload = {
        "prompt": prompt,
        "project_path": project_path,
    }
    req = urllib.request.Request(
        f"{SERVER_URL}/v1/act",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_code_blocks(text: str) -> List[tuple[str, str]]:
    """Extracts (file_path, content) from model markdown response."""
    results = []
    # Match patterns like: Here is `scripts/player.gd`: ```gdscript ... ```
    pattern = r"(?:(?:Here is|File:|Scene:)\s*[`'\"]?([a-zA-Z0-9_\-/\\]+\.(?:gd|tscn|godot))[`'\"]?[\s\S]*?)?```(?:gdscript|tscn)?\n([\s\S]*?)```"
    matches = re.finditer(pattern, text)
    for m in matches:
        fp = m.group(1) or ""
        code = m.group(2).strip()
        results.append((fp, code))
    
    # Fallback if no markdown blocks
    if not results and ("extends " in text or "config_version" in text):
        results.append(("", text.strip()))
    return results


def apply_file(project_path: str, rel_path: str, content: str) -> str:
    """Writes model output directly to the project directory."""
    target = Path(project_path) / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)


def validate_godot4(project_path: str) -> tuple[int, str, str]:
    """Runs headless Godot 4 validation on the project."""
    godot_bin = "/home/piet/.local/bin/godot4"
    cmd = [godot_bin, "--headless", "--path", project_path, "--quit"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Godot 4 validation timed out"
    except Exception as e:
        return -2, "", str(e)


def main():
    parser = argparse.ArgumentParser(description="Model Client")
    parser.add_argument("--prompt", required=True, help="Prompt text to submit to the model")
    parser.add_argument("--file", help="Target relative file path if writing code directly")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="Target project path")
    parser.add_argument("--mode", choices=["chat", "act"], default="chat", help="API endpoint mode")
    parser.add_argument("--exp-id", default="EXP-AUTO", help="Experiment ID for ledger")
    args = parser.parse_args()

    print(f"[*] Submitting prompt to model ({args.mode} mode)...")
    if args.mode == "chat":
        response = query_model_chat(args.prompt)
        print("\n=== MODEL RESPONSE PREVIEW ===")
        print(response[:400] + ("..." if len(response) > 400 else ""))
        blocks = extract_code_blocks(response)
        if blocks:
            for fp, code in blocks:
                target_file = args.file or fp or "scripts/temp_output.gd"
                out_path = apply_file(args.project, target_file, code)
                print(f"[+] Applied model output to: {out_path} ({len(code)} bytes)")
        elif args.file:
            out_path = apply_file(args.project, args.file, response.strip())
            print(f"[+] Applied raw model output to: {out_path} ({len(response)} bytes)")
        else:
            print("[!] No code blocks found in model output and no target --file specified.")
    else:
        res = query_model_action(args.prompt, args.project)
        print("\n=== MODEL ACTION RESULT ===")
        print(json.dumps(res, indent=2)[:500])

    # Run validation
    code, stdout, stderr = validate_godot4(args.project)
    print(f"\n[*] Godot 4 headless validation exit code: {code}")
    if stderr:
        print(f"Stderr: {stderr[:300]}")
    if stdout:
        print(f"Stdout: {stdout[:300]}")


if __name__ == "__main__":
    main()
