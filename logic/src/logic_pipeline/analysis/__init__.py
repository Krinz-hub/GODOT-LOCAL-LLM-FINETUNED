"""Analysis and graph building package for Godot projects."""

from logic_pipeline.analysis.project_graph import build_project_graph, ProjectGraph
from logic_pipeline.analysis.scene_graph import build_scene_graph, SceneGraph
from logic_pipeline.analysis.dependency_analysis import analyze_dependencies, DependencyReport
from logic_pipeline.analysis.architecture import derive_project_architecture, ArchitecturalSummary
from logic_pipeline.analysis.evidence import verify_evidence_grounding

__all__ = [
    "build_project_graph",
    "ProjectGraph",
    "build_scene_graph",
    "SceneGraph",
    "analyze_dependencies",
    "DependencyReport",
    "derive_project_architecture",
    "ArchitecturalSummary",
    "verify_evidence_grounding",
]
