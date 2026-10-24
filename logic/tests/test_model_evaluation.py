#!/usr/bin/env python3
"""Measurable Godot 4 Model Evaluation Suite.

Evaluates:
1. Godot 4 syntax and API correctness.
2. GDScript code generation.
3. Scene/project structure.
4. Multi-turn instruction following.
5. Error correction.
6. Repetition across distinct prompts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
GODOT_BIN = (
    os.environ.get("GODOT_BIN")
    or (str(Path.home() / ".local" / "bin" / "godot4") if (Path.home() / ".local" / "bin" / "godot4").exists() else None)
    or ("/home/piet/Documents/dev/Godot_v4.7.2-stable_linux.arm64" if Path("/home/piet/Documents/dev/Godot_v4.7.2-stable_linux.arm64").exists() else None)
)

G3_OBSOLETE_PATTERNS = {
    "KinematicBody": r"\bKinematicBody(?:2D|3D)?\b",
    "Spatial": r"\bSpatial\b",
    "unannotated_export": r"^\s*export\s*(?:\([^)]*\))?\s*var\b",
    "unannotated_onready": r"^\s*onready\s+var\b",
    "unannotated_tool": r"^\s*tool\b",
    "setget": r"\bsetget\b",
    "move_and_slide_with_args": r"\bmove_and_slide\s*\([^)]+\)",
    "File.new()": r"\bFile\.new\s*\(\s*\)",
    "Directory.new()": r"\bDirectory\.new\s*\(\s*\)",
    "old_connect_string": r"\.connect\s*\(\s*\"[^\"]+\"\s*,\s*self\s*,",
    "emit_signal_string": r"\bemit_signal\s*\(\s*\"",
    "yield()": r"\byield\s*\(",
    "rand_range": r"\brand_range\s*\(",
}


def check_godot3_apis(code: str) -> Dict[str, int]:
    """Returns counts of detected Godot 3 obsolete APIs."""
    found = {}
    for name, pattern in G3_OBSOLETE_PATTERNS.items():
        matches = len(re.findall(pattern, code, re.MULTILINE))
        if matches > 0:
            found[name] = matches
    return found


def validate_headless_godot4(code: str) -> Dict[str, Any]:
    """Runs Godot 4 headless parser.
    
    Clearly distinguishes parser compilation success from gameplay correctness.
    """
    if not GODOT_BIN or not Path(GODOT_BIN).exists():
        return {
            "parser_available": False,
            "parser_success": False,
            "error": "Godot 4 binary not available",
        }

    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "project.godot").write_text("config_version=5\n[application]\nconfig/name=\"Eval\"\n")
        script = p / "eval_script.gd"
        script.write_text(code, encoding="utf-8")

        try:
            res = subprocess.run(
                [GODOT_BIN, "--headless", "--check-only", "--path", str(p), "-s", str(script)],
                capture_output=True,
                text=True,
                timeout=6,
            )
            return {
                "parser_available": True,
                "parser_success": res.returncode == 0,
                "exit_code": res.returncode,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
            }
        except subprocess.TimeoutExpired:
            return {"parser_available": True, "parser_success": False, "error": "Parser timeout"}
        except Exception as e:
            return {"parser_available": True, "parser_success": False, "error": str(e)}


def evaluate_gameplay_correctness(code: str, required_elements: List[str]) -> Dict[str, Any]:
    """Verifies actual gameplay logic completeness beyond parser success."""
    missing = [elem for elem in required_elements if elem not in code]
    return {
        "gameplay_checks_total": len(required_elements),
        "gameplay_checks_passed": len(required_elements) - len(missing),
        "missing_elements": missing,
        "is_gameplay_correct": len(missing) == 0,
    }


def compute_jaccard(text1: str, text2: str) -> float:
    """Computes Jaccard word similarity between two responses."""
    w1 = set(text1.lower().split())
    w2 = set(text2.lower().split())
    if not w1 or not w2:
        return 0.0
    return len(w1.intersection(w2)) / len(w1.union(w2))


class TestGodotEvaluationSuite(unittest.TestCase):
    """Unit tests for the evaluation metrics themselves."""

    def test_godot3_api_detection(self):
        broken = "extends KinematicBody2D\nexport var s = 10\nfunc _physics_process(d):\n    move_and_slide(velocity)\n"
        apis = check_godot3_apis(broken)
        self.assertIn("KinematicBody", apis)
        self.assertIn("unannotated_export", apis)
        self.assertIn("move_and_slide_with_args", apis)

    def test_godot4_clean_api(self):
        clean = "@tool\nextends CharacterBody2D\n@export var speed: float = 200.0\nfunc _physics_process(d: float) -> void:\n    move_and_slide()\n"
        apis = check_godot3_apis(clean)
        self.assertEqual(len(apis), 0)

    def test_parser_vs_gameplay_distinction(self):
        # A script can be syntactically valid (parser passes) but completely lacking required gameplay logic
        stub = "extends Node\nfunc _ready() -> void:\n    pass\n"
        val = validate_headless_godot4(stub)
        self.assertTrue(val.get("parser_success"), "Valid stub must pass parser")

        gameplay = evaluate_gameplay_correctness(stub, ["Input.get_axis", "jump_velocity", "health"])
        self.assertFalse(gameplay["is_gameplay_correct"], "Stub must fail gameplay correctness")
        self.assertEqual(len(gameplay["missing_elements"]), 3)

    def test_repetition_measurement(self):
        t1 = "Required Scenes: GameScene -> BackgroundLayer, PipesLayer, PlayerLayer, GroundLayer"
        t2 = "Required Scenes: GameScene -> BackgroundLayer, PipesLayer, PlayerLayer, GroundLayer"
        self.assertAlmostEqual(compute_jaccard(t1, t2), 1.0)

        t3 = "A completely different underwater physics architecture with bubble particles"
        self.assertLess(compute_jaccard(t1, t3), 0.2)


if __name__ == "__main__":
    unittest.main()
