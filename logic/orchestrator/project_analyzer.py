"""Real Godot Project Awareness, Scene Tree Parsing, and Focused Context Retrieval."""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple


class GodotProjectAnalyzer:
    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()
        self.project_godot_path = self.project_path / "project.godot"

    def is_valid_godot_project(self) -> bool:
        return self.project_godot_path.exists()

    def get_project_metadata(self) -> Dict[str, Any]:
        """Extracts Godot engine version, autoloads, main scene, and input actions."""
        if not self.is_valid_godot_project():
            return {
                "valid": False,
                "version": "unknown",
                "name": self.project_path.name,
                "autoloads": {},
                "input_actions": [],
            }

        content = self.project_godot_path.read_text(encoding="utf-8", errors="ignore")
        config_version = 5
        version_str = "Godot 4.x"
        m_ver = re.search(r"config_version=(\d+)", content)
        if m_ver:
            config_version = int(m_ver.group(1))
            version_str = "Godot 4.x" if config_version >= 5 else "Godot 3.x"

        # Project name
        name_m = re.search(r'config/name="([^"]+)"', content)
        name = name_m.group(1) if name_m else self.project_path.name

        # Main scene
        main_scene_m = re.search(r'run/main_scene="([^"]+)"', content)
        main_scene = main_scene_m.group(1) if main_scene_m else None

        # Autoloads
        autoloads = {}
        in_autoload = False
        for line in content.splitlines():
            line_str = line.strip()
            if line_str.startswith("[autoload]"):
                in_autoload = True
                continue
            elif line_str.startswith("[") and in_autoload:
                in_autoload = False
                continue

            if in_autoload and "=" in line_str:
                parts = line_str.split("=", 1)
                auto_name = parts[0].strip()
                auto_val = parts[1].strip().strip('"').lstrip("*")
                autoloads[auto_name] = auto_val

        # Input Actions
        actions = []
        in_input = False
        for line in content.splitlines():
            line_str = line.strip()
            if line_str.startswith("[input]"):
                in_input = True
                continue
            elif line_str.startswith("[") and in_input:
                in_input = False
                continue

            if in_input and "={" in line_str:
                action_name = line_str.split("={", 1)[0].strip()
                if action_name and not action_name.startswith(";"):
                    actions.append(action_name)

        # Features
        features: List[str] = []
        feat_m = re.search(r'config/features=PackedStringArray\((.*?)\)', content)
        if feat_m:
            features = [f.strip().strip('"\'') for f in feat_m.group(1).split(",") if f.strip().strip('"\'')]

        engine_version = None
        for f in features:
            if re.match(r"^\d+\.\d+", f):
                engine_version = f
                break
        if not engine_version:
            engine_version = f"4.x (config_version {config_version})" if config_version >= 5 else f"3.x (config_version {config_version})"

        return {
            "valid": True,
            "version": version_str,
            "engine_version": engine_version,
            "features": features,
            "config_version": config_version,
            "name": name,
            "main_scene": main_scene,
            "autoloads": autoloads,
            "input_actions": sorted(actions),
        }

    def find_safe_improvement_opportunities(self) -> Dict[str, Any]:
        """Inspects real project scripts and identifies a safe, high-value, non-breaking improvement."""
        struct = self.list_project_structure()
        scripts = struct.get("scripts", [])

        # Look for player or gameplay scripts, prioritizing main controller
        player_scripts = sorted(
            [s for s in scripts if "player" in s.lower()],
            key=lambda s: (0 if Path(s).name.lower() in ("player.gd", "character.gd") else 1, len(s)),
        )
        target_script = player_scripts[0] if player_scripts else (scripts[0] if scripts else None)

        if not target_script:
            return {
                "target_file": "scripts/project_utils.gd",
                "improvement_name": "Create Project Utility Helper",
                "justification": "No existing GDScript files found; creating a safe utility helper module.",
                "acceptance_criteria": ["Godot 4 compiler validation passes"],
            }

        real_path = self.project_path / target_script
        code = real_path.read_text(encoding="utf-8", errors="ignore")

        # Opportunity A: CharacterBody2D jump cut / fall speed / speed scale
        if "CharacterBody2D" in code or "velocity" in code:
            if "jump_cut_multiplier" not in code and "velocity.y *=" in code:
                return {
                    "target_file": target_script,
                    "improvement_name": "Expose Configurable Jump Cut Multiplier",
                    "justification": (
                        f"In '{target_script}', vertical momentum reduction on early jump release is hardcoded. "
                        "Exposing an '@export var jump_cut_multiplier: float = 0.6' allows designer tuning in the Godot inspector "
                        "while strictly preserving existing movement physics behavior."
                    ),
                    "acceptance_criteria": [
                        f"Godot 4 check-only compiler validation on '{target_script}' passes",
                        "Existing jump velocities, walk speeds, and movement behaviors are preserved",
                        "Exposes '@export var jump_cut_multiplier: float = 0.6' with exact default value",
                    ],
                }
            if "speed_scale" not in code:
                return {
                    "target_file": target_script,
                    "improvement_name": "Add Configurable Speed Scale Parameter",
                    "justification": (
                        f"In '{target_script}', movement speed uses hardcoded constants. "
                        "Adding an '@export var speed_scale: float = 1.0' parameter allows designers to adjust gameplay pacing "
                        "without modifying or breaking underlying movement calculations."
                    ),
                    "acceptance_criteria": [
                        f"Godot 4 check-only compiler validation on '{target_script}' passes",
                        "Default movement physics remain identical (speed_scale = 1.0)",
                        "Preserves all existing signal connections and node references",
                    ],
                }

        # Opportunity B: General script enhancement
        return {
            "target_file": target_script,
            "improvement_name": "Add Safe Initialization and Validation Guards",
            "justification": (
                f"In '{target_script}', add runtime validation checks and type safeguards to ensure node references "
                "are valid before access, preventing null reference crashes during scene transitions."
            ),
            "acceptance_criteria": [
                f"Godot 4 compiler validation on '{target_script}' passes cleanly",
                "Existing functionality and exported variables remain intact",
            ],
        }

    def list_project_structure(self) -> Dict[str, List[str]]:
        """Lists all scenes, scripts, and resources in the project."""
        scenes: List[str] = []
        scripts: List[str] = []
        resources: List[str] = []

        if not self.project_path.exists():
            return {"scenes": [], "scripts": [], "resources": []}

        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("addons", ".godot")]
            for f in files:
                rel = str(Path(root, f).relative_to(self.project_path))
                if f.endswith(".tscn"):
                    scenes.append(rel)
                elif f.endswith(".gd"):
                    scripts.append(rel)
                elif f.endswith(".tres"):
                    resources.append(rel)

        return {
            "scenes": sorted(scenes),
            "scripts": sorted(scripts),
            "resources": sorted(resources),
        }

    def parse_scene_hierarchy(self, scene_rel_path: str) -> Dict[str, Any]:
        """Parses a .tscn file and reconstructs the real node hierarchy."""
        scene_file = self.project_path / scene_rel_path
        if not scene_file.exists():
            return {"exists": False, "error": f"Scene '{scene_rel_path}' not found"}

        content = scene_file.read_text(encoding="utf-8", errors="ignore")
        nodes: List[Dict[str, Any]] = []
        connections: List[Dict[str, str]] = []

        node_pat = re.compile(r'\[node\s+name="([^"]+)"(?:\s+type="([^"]+)")?(?:\s+parent="([^"]+)")?')
        conn_pat = re.compile(r'\[connection\s+signal="([^"]+)"\s+from="([^"]+)"\s+to="([^"]+)"\s+method="([^"]+)"')

        for match in node_pat.finditer(content):
            name = match.group(1)
            ntype = match.group(2) or "Instance"
            parent = match.group(3) or ""
            nodes.append({"name": name, "type": ntype, "parent": parent})

        for match in conn_pat.finditer(content):
            connections.append({
                "signal": match.group(1),
                "from": match.group(2),
                "to": match.group(3),
                "method": match.group(4),
            })

        # Form a tree text description
        tree_repr = self._format_scene_tree(nodes)
        return {
            "exists": True,
            "scene_path": scene_rel_path,
            "root_node": nodes[0] if nodes else None,
            "nodes": nodes,
            "connections": connections,
            "tree_description": tree_repr,
        }

    def _format_scene_tree(self, nodes: List[Dict[str, Any]]) -> str:
        if not nodes:
            return "Empty scene"
        root = nodes[0]
        children_by_parent: Dict[str, List[Dict[str, Any]]] = {}
        for n in nodes[1:]:
            p = n.get("parent", ".")
            children_by_parent.setdefault(p, []).append(n)

        lines = [f"{root['name']} ({root['type']})"]
        for child in children_by_parent.get(".", []):
            lines.append(f"  └── {child['name']} ({child['type']})")
            # 2nd level children
            sub_key = child["name"]
            for subchild in children_by_parent.get(sub_key, []):
                lines.append(f"      └── {subchild['name']} ({subchild['type']})")

        return "\n".join(lines)

    def inspect_script_interface(self, script_rel_path: str) -> Dict[str, Any]:
        """Extracts class inheritance, exports, signals, and methods from existing GDScript."""
        script_file = self.project_path / script_rel_path
        if not script_file.exists():
            return {"exists": False, "error": f"Script '{script_rel_path}' not found"}

        content = script_file.read_text(encoding="utf-8", errors="ignore")
        extends_type = "RefCounted"
        class_name_val = None
        exports: List[str] = []
        signals: List[str] = []
        methods: List[str] = []

        for line in content.splitlines():
            s = line.strip()
            if s.startswith("extends "):
                extends_type = s.split("extends ", 1)[1].strip().strip('"')
            elif s.startswith("class_name "):
                class_name_val = s.split("class_name ", 1)[1].strip()
            elif s.startswith("@export"):
                exports.append(s)
            elif s.startswith("signal "):
                signals.append(s)
            elif s.startswith("func "):
                # Extract signature up to colon
                sig = s.split(":", 1)[0].replace("func ", "").strip()
                methods.append(sig)

        return {
            "exists": True,
            "path": script_rel_path,
            "extends": extends_type,
            "class_name": class_name_val,
            "exports": exports,
            "signals": signals,
            "methods": methods,
            "total_lines": len(content.splitlines()),
            "content": content,
        }

    def build_focused_context_for_task(self, target_files: List[str], task_description: str) -> str:
        """Constructs a compact, rich prompt context (< 1,500 tokens) for a specific task."""
        meta = self.get_project_metadata()
        struct = self.list_project_structure()

        parts = [
            f"### Godot Project Overview",
            f"- Project Name: {meta['name']}",
            f"- Engine Version: {meta['version']} (config_version={meta.get('config_version', 5)})",
        ]

        if meta.get("autoloads"):
            auto_str = ", ".join(f"{k} ({v})" for k, v in meta["autoloads"].items())
            parts.append(f"- Autoload Singletons: {auto_str}")

        if meta.get("input_actions"):
            parts.append(f"- Configured Input Actions: {', '.join(meta['input_actions'][:12])}")

        # Add target file interfaces & scene trees
        for f in target_files:
            clean_f = f.strip().lstrip("/")
            if clean_f.endswith(".tscn"):
                tree_info = self.parse_scene_hierarchy(clean_f)
                if tree_info.get("exists"):
                    parts.append(f"\n### Existing Scene Hierarchy: {clean_f}")
                    parts.append(tree_info["tree_description"])
                    if tree_info.get("connections"):
                        conns = [f"{c['signal']} -> {c['to']}.{c['method']}()" for c in tree_info["connections"]]
                        parts.append(f"Signals: {', '.join(conns)}")

            elif clean_f.endswith(".gd"):
                script_info = self.inspect_script_interface(clean_f)
                if script_info.get("exists"):
                    parts.append(f"\n### Existing Script: {clean_f}")
                    parts.append(f"- Extends: {script_info['extends']}")
                    if script_info.get("exports"):
                        parts.append(f"- Exports: {', '.join(script_info['exports'])}")
                    if script_info.get("signals"):
                        parts.append(f"- Signals: {', '.join(script_info['signals'])}")
                    if script_info.get("methods"):
                        parts.append(f"- Existing Methods: {', '.join(script_info['methods'][:10])}")
                    # If script is under 60 lines, provide full context for surgical editing
                    if script_info["total_lines"] <= 60:
                        parts.append(f"```gdscript\n{script_info['content']}\n```")

        # General project inventory summary
        parts.append(f"\n### Available Project Files")
        all_files = struct["scenes"][:6] + struct["scripts"][:8]
        parts.append(f"Files: {', '.join(all_files) if all_files else 'Empty project'}")

        return "\n".join(parts)
