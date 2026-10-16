"""Project graph analysis using NetworkX."""

from typing import Any, Dict, List, Optional
import networkx as nx
from logic_pipeline.logging_config import get_logger

logger = get_logger("analysis.project_graph")


class ProjectGraph:
    """Represents a Godot project as a directed dependency graph."""

    def __init__(self, project_id: str = "default"):
        self.project_id = project_id
        self.graph = nx.DiGraph()

    def add_node(self, node_id: str, node_type: str, metadata: Optional[Dict[str, Any]] = None):
        self.graph.add_node(node_id, type=node_type, metadata=metadata or {})

    def add_edge(self, source: str, target: str, relation: str):
        self.graph.add_edge(source, target, relation=relation)

    def get_entry_reachable_nodes(self, entry_scene: str) -> List[str]:
        """Finds all nodes reachable from the project's entry scene."""
        clean_entry = entry_scene.replace("res://", "")
        if clean_entry in self.graph:
            return [str(n) for n in nx.descendants(self.graph, clean_entry)] + [clean_entry]
        return []

    def get_orphaned_nodes(self) -> List[str]:
        """Finds nodes that have no incoming or outgoing connections."""
        return [str(n) for n in self.graph.nodes if self.graph.degree(n) == 0]

    def has_cycles(self) -> bool:
        """Checks for cyclic dependencies in the project."""
        return not nx.is_directed_acyclic_graph(self.graph)

    def find_circular_dependencies(self) -> List[List[str]]:
        """Finds all simple cycles in the project graph."""
        return [[str(n) for n in cycle] for cycle in nx.simple_cycles(self.graph)]

    @property
    def nodes(self):
        return self.graph.nodes

    @property
    def edges(self):
        return self.graph.edges

    def to_dict(self) -> Dict[str, Any]:
        """Converts graph into JSON-serializable node/edge format."""
        return {
            "project_id": self.project_id,
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "nodes": [
                {"id": n, "type": self.graph.nodes[n].get("type", "unknown")}
                for n in self.graph.nodes
            ],
            "edges": [
                {"source": u, "target": v, "relation": self.graph.edges[u, v].get("relation", "depends_on")}
                for u, v in self.graph.edges
            ],
            "has_cycles": self.has_cycles(),
        }


def build_project_graph(project_record: Dict[str, Any]) -> ProjectGraph:
    """Builds a ProjectGraph from an extracted project record."""
    project_id = project_record.get("project_id", "unknown")
    pg = ProjectGraph(project_id)

    entry_scene = project_record.get("entry_scene", "")
    autoloads = project_record.get("autoloads", {})

    # Add all files as nodes
    for f in project_record.get("files", []):
        f_path = f["path"]
        pg.add_node(f_path, node_type=f["type"], metadata={"size": f["size_bytes"]})

    # Add autoloads
    raw_autoloads = project_record.get("autoloads", {})
    if isinstance(raw_autoloads, dict):
        autoload_items = raw_autoloads.items()
    elif isinstance(raw_autoloads, list):
        autoload_items = [(a.get("name", ""), a.get("path", "")) for a in raw_autoloads if isinstance(a, dict)]
    else:
        autoload_items = []

    for name, path in autoload_items:
        clean_p = path.replace("res://", "")
        if clean_p in pg.graph:
            pg.add_edge("project.godot", clean_p, relation="autoload_singleton")

    # Add scene dependencies
    for s_dep in project_record.get("scene_dependencies", []):
        scene_path = s_dep["scene"]
        attached_script = s_dep.get("attached_script")
        if attached_script:
            clean_s = attached_script.replace("res://", "")
            if clean_s in pg.graph:
                pg.add_edge(scene_path, clean_s, relation="attached_script")

        for dep in s_dep.get("dependencies", []):
            clean_dep = dep.replace("res://", "")
            if clean_dep in pg.graph:
                pg.add_edge(scene_path, clean_dep, relation="scene_dependency")

    return pg
