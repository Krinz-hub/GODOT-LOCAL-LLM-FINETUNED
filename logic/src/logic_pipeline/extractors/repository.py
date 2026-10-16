"""Full Godot repository project extractor."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from logic_pipeline.extractors.project_config import parse_project_godot
from logic_pipeline.extractors.scene import parse_scene_file
from logic_pipeline.logging_config import get_logger

logger = get_logger("extractors.repository")


def extract_repository_project(
    project_dir: Path,
    project_id: str,
    repository: Optional[str] = None,
    source_url: str = "",
    license_val: str = "Unknown",
) -> Optional[Dict[str, Any]]:
    """Extracts a complete Godot project representation matching project.schema.json."""
    project_godot_path = project_dir / "project.godot"
    if not project_godot_path.exists():
        logger.warning("No project.godot found in %s", project_dir)
        return None

    try:
        with open(project_godot_path, "r", encoding="utf-8", errors="ignore") as f:
            cfg_content = f.read()
    except Exception as e:
        logger.error("Failed to read %s: %s", project_godot_path, e)
        return None

    cfg_info = parse_project_godot(cfg_content)

    files_list: List[Dict[str, Any]] = []
    scripts: List[str] = []
    scenes: List[str] = []
    resources: List[str] = []
    scene_deps: List[Dict[str, Any]] = []

    for root, dirs, files in os.walk(project_dir):
        # Filter hidden/temporary folders
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["build", "node_modules", "temp"]]

        for file_name in files:
            full_path = Path(root) / file_name
            rel_path = full_path.relative_to(project_dir).as_posix()
            ext = full_path.suffix.lower()

            f_type = "unknown"
            if ext == ".gd":
                f_type = "gdscript"
                scripts.append(rel_path)
            elif ext == ".tscn":
                f_type = "godot_scene"
                scenes.append(rel_path)
            elif ext == ".tres":
                f_type = "godot_resource"
                resources.append(rel_path)
            elif ext == ".gdshader":
                f_type = "shader"
            elif file_name == "project.godot":
                f_type = "project_config"

            size_bytes = full_path.stat().st_size if full_path.exists() else 0
            files_list.append({
                "path": rel_path,
                "type": f_type,
                "size_bytes": size_bytes,
                "content": None,
            })

            # If it's a scene, extract scene dependencies
            if ext == ".tscn" and size_bytes < 1000000:
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as sf:
                        scene_data = parse_scene_file(sf.read())
                        scene_deps.append({
                            "scene": rel_path,
                            "root_type": scene_data.root_node_type,
                            "attached_script": scene_data.attached_script,
                            "dependencies": scene_data.dependencies,
                            "hierarchy": scene_data.hierarchy_summary,
                        })
                except Exception:
                    pass

    return {
        "record_type": "godot_project",
        "project_id": project_id,
        "project_name": cfg_info.project_name or project_dir.name,
        "project_path": str(project_dir),
        "repository": repository,
        "godot_version": cfg_info.godot_version,
        "version_confidence": 0.95,
        "version_source": "project.godot",
        "entry_scene": cfg_info.main_scene,
        "project_file": "project.godot",
        "files": files_list,
        "scripts": sorted(scripts),
        "scenes": sorted(scenes),
        "resources": sorted(resources),
        "autoloads": cfg_info.autoloads,
        "scene_dependencies": scene_deps,
        "source": "local" if not repository else "github",
        "source_url": source_url,
        "license": license_val,
        "metadata": {
            "features": cfg_info.features,
            "plugins": cfg_info.plugins,
        },
    }
