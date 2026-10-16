"""Dependency analysis and circularity checks for Godot projects and plans."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set
import networkx as nx
from logic_pipeline.logging_config import get_logger

logger = get_logger("analysis.dependencies")


@dataclass
class DependencyReport:
    is_valid: bool = True
    unresolved_references: List[str] = field(default_factory=list)
    circular_dependencies: List[List[str]] = field(default_factory=list)
    task_order: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def analyze_dependencies(
    files_known: Set[str],
    scene_dependencies: List[Dict[str, Any]],
    autoloads: Dict[str, str],
) -> DependencyReport:
    """Audits scene and script references in a project."""
    report = DependencyReport()
    dep_graph = nx.DiGraph()

    # Normalize known files
    clean_known = {f.replace("res://", "").lstrip("/") for f in files_known}

    # Verify autoloads
    for name, path in autoloads.items():
        clean_p = path.replace("res://", "").lstrip("/")
        if clean_p not in clean_known:
            report.unresolved_references.append(f"Autoload '{name}' missing file: {path}")
            report.is_valid = False

    # Verify scene dependencies
    for s_dep in scene_dependencies:
        src_scene = s_dep["scene"].replace("res://", "").lstrip("/")
        attached = s_dep.get("attached_script")
        if attached:
            clean_att = attached.replace("res://", "").lstrip("/")
            if clean_att not in clean_known:
                report.unresolved_references.append(f"Scene '{src_scene}' attached script missing: {attached}")
                report.is_valid = False
            else:
                dep_graph.add_edge(src_scene, clean_att)

        for ref in s_dep.get("dependencies", []):
            clean_ref = ref.replace("res://", "").lstrip("/")
            if clean_ref not in clean_known:
                report.unresolved_references.append(f"Scene '{src_scene}' references missing: {ref}")
                report.is_valid = False
            else:
                dep_graph.add_edge(src_scene, clean_ref)

    # Check for cycles
    try:
        cycles = list(nx.simple_cycles(dep_graph))
        if cycles:
            report.circular_dependencies = [[str(node) for node in c] for c in cycles]
            report.is_valid = False
            logger.warning("Found %d circular dependencies in project", len(cycles))
    except Exception as e:
        logger.debug("Cycle check failed: %s", e)

    return report


def analyze_task_prerequisites(tasks: List[Dict[str, Any]]) -> DependencyReport:
    """Verifies that implementation tasks have consistent, acyclic ordering."""
    report = DependencyReport()
    task_graph = nx.DiGraph()
    task_ids = set()

    for t in tasks:
        t_id = t.get("id")
        if t_id:
            task_ids.add(t_id)
            task_graph.add_node(t_id)

    for t in tasks:
        t_id = t.get("id")
        prereqs = t.get("prerequisites", [])
        for p in prereqs:
            if p not in task_ids:
                report.unresolved_references.append(f"Task '{t_id}' has missing prerequisite '{p}'")
                report.is_valid = False
            else:
                # p must be done BEFORE t_id: edge p -> t_id
                task_graph.add_edge(p, t_id)

    # Check for cycles in task prerequisites
    try:
        cycles = list(nx.simple_cycles(task_graph))
        if cycles:
            report.circular_dependencies = [[str(node) for node in c] for c in cycles]
            report.is_valid = False
        else:
            report.task_order = [str(node) for node in nx.topological_sort(task_graph)]
    except Exception as e:
        report.is_valid = False
        report.warnings.append(f"Task topological sort failed: {e}")

    return report
