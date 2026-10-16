"""Godot 4 compatibility checker for GDScript and scenes."""

from dataclasses import dataclass, field
import re
from typing import List


@dataclass
class CompatibilityReport:
    is_compatible: bool = True
    godot_version: str = "Godot 4.x"
    legacy_features_found: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


def check_godot_compatibility(code: str) -> CompatibilityReport:
    """Audits GDScript code for Godot 3 vs Godot 4 incompatibilities."""
    report = CompatibilityReport()

    checks = [
        (
            r"(?<!@)\bexport\s*(?:\([^)]*\))?\s*var\b",
            "Godot 3 'export var' detected (use '@export var')",
            "Replace 'export var' with '@export var'",
        ),
        (
            r"(?<!@)\bonready\s+var\b",
            "Godot 3 'onready var' detected (use '@onready var')",
            "Replace 'onready var' with '@onready var'",
        ),
        (
            r"\bsetget\b",
            "Godot 3 'setget' property syntax detected",
            "Replace with Godot 4 property getters/setters: 'var x: get = _get_x, set = _set_x'",
        ),
        (
            r"\byield\s*\(",
            "Godot 3 'yield()' detected",
            "Replace with Godot 4 'await'",
        ),
        (
            r"\bPool[A-Za-z0-9_]*Array\b",
            "Godot 3 'Pool*Array' detected",
            "Replace with Godot 4 'Packed*Array'",
        ),
        (
            r"\binstance\(\)",
            "Godot 3 'PackedScene.instance()' detected",
            "Replace with 'PackedScene.instantiate()'",
        ),
    ]

    for pattern, msg, rec in checks:
        if re.search(pattern, code):
            report.is_compatible = False
            report.godot_version = "Godot 3.x (Legacy)"
            report.legacy_features_found.append(msg)
            report.recommendations.append(rec)

    return report
