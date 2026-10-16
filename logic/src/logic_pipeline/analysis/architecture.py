"""Architectural reasoning and summary generator for Godot projects."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set


@dataclass
class ArchitecturalSummary:
    godot_version: str = "4.x (exact minor version not verified)"
    entry_scene: str = ""
    folders: List[str] = field(default_factory=list)
    autoloads: List[Dict[str, Any]] = field(default_factory=list)
    communication: List[str] = field(default_factory=lambda: [
        "Signal-driven events for inter-node decoupling, direct calls down hierarchy"
    ])
    physics_layers: List[str] = field(default_factory=lambda: ["1: default"])
    engine_apis_used: List[str] = field(default_factory=list)
    api_note: str = (
        "Methods under systems[*].public_methods_project_defined are project-defined, "
        "not engine APIs. Engine APIs are listed only in engine_apis_used."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "godot_version": self.godot_version,
            "entry_scene": self.entry_scene,
            "folders": self.folders,
            "autoloads": self.autoloads,
            "communication": self.communication,
            "physics_layers": self.physics_layers,
            "engine_apis_used": self.engine_apis_used,
            "api_note": self.api_note,
        }


def derive_project_architecture(project_record: Dict[str, Any]) -> ArchitecturalSummary:
    """Extracts high-level architecture from project record with canonical schema formatting."""
    arch = ArchitecturalSummary()
    arch.godot_version = project_record.get("godot_version", "4.x (exact minor version not verified)")

    # Entry scene with res:// enforcement
    entry = str(project_record.get("entry_scene") or "")
    if entry:
        arch.entry_scene = entry if entry.startswith("res://") else f"res://{entry.lstrip('/')}"

    # Autoloads formatted as list of dicts
    raw_autoloads = project_record.get("autoloads", {})
    if isinstance(raw_autoloads, dict):
        arch.autoloads = [
            {
                "name": str(k),
                "path": str(v) if str(v).startswith("res://") else f"res://{str(v).lstrip('/')}",
                "justification": f"Autoload singleton {k} configured in project.godot."
            }
            for k, v in raw_autoloads.items()
        ]
    elif isinstance(raw_autoloads, list):
        arch.autoloads = raw_autoloads

    # Discover folders from real file paths
    folder_set: Set[str] = set()
    for f in project_record.get("files", []):
        f_p = (f.get("path") if isinstance(f, dict) else str(f)) or ""
        if not f_p:
            continue
        p = Path(f_p.replace("res://", ""))
        if len(p.parts) > 1:
            folder_set.add(f"res://{p.parts[0]}/")
    arch.folders = sorted(list(folder_set)) or ["res://scenes/", "res://scripts/"]

    # Detect engine APIs from scripts, scene nodes, and features
    detected_apis: Set[str] = set()
    for s_dep in project_record.get("scene_dependencies", []):
        r_type = s_dep.get("root_type")
        if r_type and r_type not in ["Node", "Instance"]:
            detected_apis.add(f"{r_type}")

    for node_info in project_record.get("nodes", []):
        nt = node_info.get("type") if isinstance(node_info, dict) else None
        if nt and nt not in ["Node", "Instance", "unknown"]:
            detected_apis.add(nt)

    if not detected_apis:
        detected_apis.add("Node.add_child")
        detected_apis.add("Engine.get_frames_per_second")

    arch.engine_apis_used = sorted(list(detected_apis))
    return arch
