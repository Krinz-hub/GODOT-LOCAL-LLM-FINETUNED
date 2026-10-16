"""Parser for Godot project.godot configuration files."""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional


@dataclass
class ProjectGodotInfo:
    config_version: int = 5
    project_name: str = "Unnamed Project"
    main_scene: str = ""
    godot_version: str = "4.x"
    features: List[str] = field(default_factory=list)
    autoloads: Dict[str, str] = field(default_factory=dict)
    input_actions: List[str] = field(default_factory=list)
    physics_settings: Dict[str, Any] = field(default_factory=dict)
    plugins: List[str] = field(default_factory=list)
    raw_sections: Dict[str, Dict[str, str]] = field(default_factory=dict)


def parse_project_godot(content: str) -> ProjectGodotInfo:
    """Parses project.godot text into structured ProjectGodotInfo."""
    info = ProjectGodotInfo()
    current_section = "root"
    sections: Dict[str, Dict[str, str]] = {"root": {}}

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue

        # Section header e.g. [application]
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            if current_section not in sections:
                sections[current_section] = {}
            continue

        # Key-value pair e.g. config/name="My Game"
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"')
            sections[current_section][key] = val

    info.raw_sections = sections

    # Extract config version
    if "config_version" in sections["root"]:
        try:
            info.config_version = int(sections["root"]["config_version"])
        except ValueError:
            pass

    # Extract application details
    app_sec = sections.get("application", {})
    info.project_name = app_sec.get("config/name", "Unnamed Project")
    info.main_scene = app_sec.get("run/main_scene", "")

    # Extract features / version
    feat_str = app_sec.get("config/features", "")
    if feat_str:
        # Match quoted strings in PackedStringArray("4.3", "Forward Plus")
        matches = re.findall(r'"([^"]+)"', feat_str)
        info.features = matches
        for m in matches:
            if m.startswith("4."):
                info.godot_version = f"Godot {m}"
                break
    elif info.config_version == 5:
        info.godot_version = "Godot 4.x"
    elif info.config_version == 4:
        info.godot_version = "Godot 3.x"

    # Extract autoloads
    autoload_sec = sections.get("autoload", {})
    for name, path in autoload_sec.items():
        # Path often has leading asterisk for singleton: "*res://path.gd"
        clean_path = path.lstrip("*").strip('"')
        info.autoloads[name] = clean_path

    # Extract physics
    phys_sec = sections.get("physics", {})
    info.physics_settings = phys_sec

    # Extract plugins
    plugins_sec = sections.get("editor_plugins", {})
    if "enabled" in plugins_sec:
        info.plugins = re.findall(r'"([^"]+)"', plugins_sec["enabled"])

    # Extract input actions
    input_sec = sections.get("input", {})
    info.input_actions = sorted(list(input_sec.keys()))

    return info
