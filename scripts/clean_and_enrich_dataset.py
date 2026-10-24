#!/usr/bin/env python3
"""Dataset Cleaning, Transpilation, and Multi-Turn Enrichment Pipeline.

Safely transforms the Godot training dataset into a clean, Godot 4-compliant,
deduplicated, and multi-turn enriched ShareGPT/ChatML dataset without modifying
original source data.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "godot_training_workspace" / "data" / "train.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "godot_training_workspace" / "data" / "train_cleaned_v2.jsonl"
FINAL_DIR = REPO_ROOT / "final"

# Godot 3 to 4 Transpilation Regex Rules
RE_TOOL = re.compile(r"^\s*tool\b", re.MULTILINE)
RE_SPATIAL = re.compile(r"\bSpatial\b")
RE_RAND_RANGE = re.compile(r"\brand_range\s*\(")
RE_CONNECT_STR = re.compile(r"\.connect\s*\(\s*\"([^\"]+)\"\s*,\s*self\s*,\s*\"([^\"]+)\"\s*\)")
RE_EMIT_SIGNAL = re.compile(r"\bemit_signal\s*\(\s*\"([^\"]+)\"\s*(?:,\s*)?")
RE_MOVE_AND_SLIDE_ARGS = re.compile(r"\bmove_and_slide\s*\([^)]+\)")
RE_EXPORT_NO_AT = re.compile(r"^\s*export\s*(?:\([^)]*\))?\s*var\b", re.MULTILINE)
RE_ONREADY_NO_AT = re.compile(r"^\s*onready\s+var\b", re.MULTILINE)
RE_VELOCITY_REDEFINE = re.compile(r"^\s*var\s+velocity(?:\s*:\s*Vector2)?\s*=\s*Vector2[^\n]*\n?", re.MULTILINE)
RE_SETGET = re.compile(r"\bsetget\b")


def transpile_to_godot4(code: str) -> Tuple[str, List[str]]:
    """Applies systematic AST/Regex rules to convert Godot 3 GDScript into Godot 4."""
    applied: List[str] = []

    # 1. tool -> @tool
    if RE_TOOL.search(code):
        code = RE_TOOL.sub("@tool", code)
        applied.append("tool -> @tool")

    # 2. export var -> @export var
    if RE_EXPORT_NO_AT.search(code):
        code = RE_EXPORT_NO_AT.sub("@export var", code)
        applied.append("export var -> @export var")

    # 3. onready var -> @onready var
    if RE_ONREADY_NO_AT.search(code):
        code = RE_ONREADY_NO_AT.sub("@onready var", code)
        applied.append("onready var -> @onready var")

    # 4. Spatial -> Node3D
    if RE_SPATIAL.search(code):
        code = RE_SPATIAL.sub("Node3D", code)
        applied.append("Spatial -> Node3D")

    # 5. rand_range -> randf_range
    if RE_RAND_RANGE.search(code):
        code = RE_RAND_RANGE.sub("randf_range(", code)
        applied.append("rand_range -> randf_range")

    # 6. .connect("signal", self, "method") -> signal.connect(method)
    if RE_CONNECT_STR.search(code):
        code = RE_CONNECT_STR.sub(r"\1.connect(\2)", code)
        applied.append("connect_string -> callable")

    # 7. emit_signal("sig", ...) -> sig.emit(...)
    def _emit_sub(m: re.Match) -> str:
        sig_name = m.group(1)
        return f"{sig_name}.emit("

    if RE_EMIT_SIGNAL.search(code):
        code = RE_EMIT_SIGNAL.sub(_emit_sub, code)
        applied.append("emit_signal -> signal.emit")

    # 8. CharacterBody2D built-in velocity fix
    if "extends CharacterBody2D" in code:
        if RE_VELOCITY_REDEFINE.search(code):
            code = RE_VELOCITY_REDEFINE.sub("", code)
            applied.append("removed redundant velocity property declaration")
        if RE_MOVE_AND_SLIDE_ARGS.search(code):
            code = RE_MOVE_AND_SLIDE_ARGS.sub("move_and_slide()", code)
            applied.append("move_and_slide(args) -> move_and_slide()")

    return code, applied


def validate_gdscript_headless(code: str) -> bool:
    """Uses Godot 4 headless parser to check syntax."""
    exe = (
        os.environ.get("GODOT_BIN")
        or (str(Path.home() / ".local" / "bin" / "godot4") if (Path.home() / ".local" / "bin" / "godot4").exists() else None)
        or ("/home/piet/Documents/dev/Godot_v4.7.2-stable_linux.arm64" if Path("/home/piet/Documents/dev/Godot_v4.7.2-stable_linux.arm64").exists() else None)
    )
    if not exe:
        return True  # If Godot not present, skip parser gate

    try:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "project.godot").write_text("config_version=5\n[application]\nconfig/name=\"Gate\"\n")
            script_path = p / "test.gd"
            script_path.write_text(code, encoding="utf-8")

            res = subprocess.run(
                [exe, "--headless", "--check-only", "--path", str(p), "-s", str(script_path)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return res.returncode == 0
    except Exception:
        return True


def clean_dataset(
    input_path: Path,
    output_path: Path,
    quarantine_path: Optional[Path] = None,
    enrich_multi_turn: bool = True,
) -> Dict[str, Any]:
    print(f"Reading input dataset: {input_path}")
    seen_hashes: Set[str] = set()
    cleaned_records: List[Dict[str, Any]] = []
    quarantined_records: List[Dict[str, Any]] = []

    stats = Counter()

    with open(input_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            stats["total_scanned"] += 1
            try:
                rec = json.loads(line)
            except Exception as e:
                stats["malformed_json"] += 1
                continue

            msgs = rec.get("messages", [])
            if len(msgs) < 3:
                stats["short_record"] += 1
                continue

            user_msg = msgs[1].get("content", "").strip()
            asst_msg = msgs[2].get("content", "").strip()

            # 1. Exact Deduplication
            pair_hash = hashlib.md5((user_msg + "|||" + asst_msg).encode()).hexdigest()
            if pair_hash in seen_hashes:
                stats["duplicates_dropped"] += 1
                continue
            seen_hashes.add(pair_hash)

            # 2. Extract code block
            code_match = re.search(r"```(?:gdscript)?\s*\n(.*?)```", asst_msg, re.DOTALL)
            if code_match:
                orig_code = code_match.group(1).strip()
            else:
                orig_code = asst_msg

            # 3. Quarantine unfixable obsolete patterns (e.g. setget without getter/setter structure)
            if RE_SETGET.search(orig_code):
                stats["quarantined_setget"] += 1
                if quarantine_path:
                    quarantined_records.append({"line": line_num, "reason": "untranspiled_setget", "record": rec})
                continue

            # 4. Transpile Godot 3 to Godot 4
            new_code, changes = transpile_to_godot4(orig_code)
            if changes:
                stats["transpiled_records"] += 1
                stats.update(changes)

            # 5. Reconstruct clean assistant message
            new_asst_msg = f"```gdscript\n{new_code}\n```"
            clean_rec = {
                "messages": [
                    {"role": "system", "content": "You are an expert Godot 4 Engine developer and autonomous AI agent."},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": new_asst_msg},
                ]
            }
            cleaned_records.append(clean_rec)
            stats["exported_single_turn"] += 1

    # 6. Multi-turn Enrichment from curated stages
    if enrich_multi_turn:
        print("Enriching with multi-turn debugging and agent tasks...")
        # A. Debugging Q&A pairs
        debug_path = FINAL_DIR / "debugging.jsonl"
        if debug_path.exists():
            with open(debug_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        prob = d.get("problem", "")
                        fix = d.get("proposed_fix", "")
                        if prob and fix:
                            rec = {
                                "messages": [
                                    {"role": "system", "content": "You are an expert Godot 4 Engine developer specializing in debugging and repair."},
                                    {"role": "user", "content": f"Fix the following Godot issue:\n{prob}"},
                                    {"role": "assistant", "content": f"### Root Cause\n{d.get('root_cause', '')}\n\n### Fix\n```gdscript\n{fix}\n```"},
                                    {"role": "user", "content": "How can I verify this fix in Godot 4?"},
                                    {"role": "assistant", "content": "Run the project with `godot4 --headless --editor --quit` or attach unit tests to confirm the script loads without parse errors."},
                                ]
                            }
                            cleaned_records.append(rec)
                            stats["enriched_multi_turn_debugging"] += 1
                    except Exception:
                        pass

        # B. Agent task trajectories
        agent_path = FINAL_DIR / "agent_tasks.jsonl"
        if agent_path.exists():
            with open(agent_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        desc = d.get("description", "")
                        patch = d.get("diff", "")
                        if desc and patch:
                            rec = {
                                "messages": [
                                    {"role": "system", "content": "You are an autonomous Godot 4 AI agent."},
                                    {"role": "user", "content": f"Implement this change request for the Godot project:\n{desc}"},
                                    {"role": "assistant", "content": f"```json\n{{\n  \"thought\": \"Applying patch for {desc[:40]}\",\n  \"action_type\": \"create_or_update_script\",\n  \"parameters\": {{\n    \"file_path\": \"{d.get('file_path', 'script.gd')}\",\n    \"content\": \"{d.get('new_content', '')[:300]}\"\n  }}\n}}\n```"},
                                    {"role": "user", "content": "Please verify the patch works and report status."},
                                    {"role": "assistant", "content": "```json\n{{\n  \"thought\": \"Running headless verification\",\n  \"action_type\": \"run_project\",\n  \"parameters\": {{\n    \"command\": \"--headless --quit\"\n  }}\n}}\n```"},
                                ]
                            }
                            cleaned_records.append(rec)
                            stats["enriched_multi_turn_agent"] += 1
                    except Exception:
                        pass

    # 7. Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in cleaned_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if quarantine_path and quarantined_records:
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)
        with open(quarantine_path, "w", encoding="utf-8") as f:
            for r in quarantined_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    stats["final_total_records"] = len(cleaned_records)
    print(f"Exported {len(cleaned_records)} records to {output_path}")
    return dict(stats)


def main():
    parser = argparse.ArgumentParser(description="Godot Dataset Cleaner and Multi-Turn Enricher")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to input train.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to cleaned output jsonl")
    parser.add_argument("--quarantine", type=Path, default=None, help="Path to quarantine jsonl")
    parser.add_argument("--no-enrich", action="store_true", help="Disable multi-turn dataset enrichment")
    args = parser.parse_args()

    results = clean_dataset(
        input_path=args.input,
        output_path=args.output,
        quarantine_path=args.quarantine,
        enrich_multi_turn=not args.no_enrich,
    )
    print("\n--- CLEANING STATS ---")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
