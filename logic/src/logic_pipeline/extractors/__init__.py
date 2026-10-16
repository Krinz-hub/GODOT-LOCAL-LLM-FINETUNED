"""Extractors package for Godot projects, scripts, scenes, and resources."""

from logic_pipeline.extractors.project_config import parse_project_godot, ProjectGodotInfo
from logic_pipeline.extractors.gdscript import parse_gdscript, GDScriptAnalysis
from logic_pipeline.extractors.scene import parse_scene_file, SceneAnalysis
from logic_pipeline.extractors.resource import parse_resource_file, ResourceAnalysis
from logic_pipeline.extractors.repository import extract_repository_project
from logic_pipeline.extractors.documentation import extract_documentation_sections
from logic_pipeline.extractors.issues import parse_issue_record
from logic_pipeline.extractors.patches import parse_git_diff

__all__ = [
    "parse_project_godot",
    "ProjectGodotInfo",
    "parse_gdscript",
    "GDScriptAnalysis",
    "parse_scene_file",
    "SceneAnalysis",
    "parse_resource_file",
    "ResourceAnalysis",
    "extract_repository_project",
    "extract_documentation_sections",
    "parse_issue_record",
    "parse_git_diff",
]
