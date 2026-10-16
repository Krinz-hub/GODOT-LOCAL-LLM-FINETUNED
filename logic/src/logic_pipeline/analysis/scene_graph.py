"""Scene hierarchy and node graph builder."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import networkx as nx
from logic_pipeline.extractors.scene import SceneAnalysis


class SceneGraph:
    """Graph representation of nodes and connections within a single scene."""

    def __init__(self, scene_path: str):
        self.scene_path = scene_path
        self.graph = nx.DiGraph()

    def build_from_analysis(self, analysis: SceneAnalysis):
        for node in analysis.nodes:
            self.graph.add_node(
                node.name,
                node_type=node.node_type,
                script_id=node.script_id,
                instance_id=node.instance_id,
            )
            if node.parent:
                parent_name = node.parent.strip("./") or analysis.root_node_name
                self.graph.add_edge(parent_name, node.name, relation="parent_child")

        for conn in analysis.connections:
            self.graph.add_edge(
                conn.from_node,
                conn.to_node,
                relation="signal_connection",
                signal=conn.signal,
                method=conn.method,
            )

    def get_root_node(self) -> Optional[str]:
        # Node with in-degree 0 for parent_child relation
        for n in self.graph.nodes:
            if self.graph.in_degree(n) == 0:
                return n
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_path": self.scene_path,
            "node_count": self.graph.number_of_nodes(),
            "nodes": [
                {"name": n, "type": self.graph.nodes[n].get("node_type", "Node")}
                for n in self.graph.nodes
            ],
            "edges": [
                {
                    "source": u,
                    "target": v,
                    "relation": self.graph.edges[u, v].get("relation", "parent_child"),
                }
                for u, v in self.graph.edges
            ],
        }


def build_scene_graph(scene_path: str, analysis: SceneAnalysis) -> SceneGraph:
    sg = SceneGraph(scene_path)
    sg.build_from_analysis(analysis)
    return sg
