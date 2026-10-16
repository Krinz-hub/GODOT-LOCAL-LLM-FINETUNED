"""Parser for Godot .tscn (text scene) files."""

from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional


@dataclass
class SceneNode:
    name: str
    node_type: str
    parent: Optional[str] = None
    script_id: Optional[str] = None
    instance_id: Optional[str] = None


@dataclass
class SceneConnection:
    signal: str
    from_node: str
    to_node: str
    method: str


@dataclass
class SceneAnalysis:
    root_node_name: str = ""
    root_node_type: str = "Node"
    attached_script: Optional[str] = None
    nodes: List[SceneNode] = field(default_factory=list)
    ext_resources: Dict[str, Dict[str, str]] = field(default_factory=dict)
    sub_resources: List[str] = field(default_factory=list)
    connections: List[SceneConnection] = field(default_factory=list)
    instanced_scenes: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    hierarchy_summary: str = ""
    hierarchy_tree: List[str] = field(default_factory=list)


def parse_scene_file(content: str) -> SceneAnalysis:
    """Parses a Godot .tscn text scene into structured metadata."""
    analysis = SceneAnalysis()

    # Regex patterns
    ext_res_pattern = re.compile(r'\[ext_resource\s+type="([^"]+)"\s+(?:uid="[^"]+"\s+)?path="([^"]+)"\s+id="([^"]+)"\]')
    node_header_pattern = re.compile(r'\[node\s+name="([^"]+)"(?:\s+type="([^"]+)")?(?:\s+parent="([^"]+)")?(?:\s+instance=ExtResource\("([^"]+)"\))?\]')
    conn_pattern = re.compile(r'\[connection\s+signal="([^"]+)"\s+from="([^"]+)"\s+to="([^"]+)"\s+method="([^"]+)"\]')
    script_assign_pattern = re.compile(r'script\s*=\s*ExtResource\("([^"]+)"\)')

    current_node: Optional[SceneNode] = None

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue

        # Check external resource
        m_ext = ext_res_pattern.match(line)
        if m_ext:
            res_type, res_path, res_id = m_ext.groups()
            analysis.ext_resources[res_id] = {"type": res_type, "path": res_path}
            analysis.dependencies.append(res_path)
            if res_type == "PackedScene" or res_path.endswith(".tscn"):
                analysis.instanced_scenes.append(res_path)
            continue

        # Check connection
        m_conn = conn_pattern.match(line)
        if m_conn:
            sig, from_n, to_n, method = m_conn.groups()
            analysis.connections.append(SceneConnection(signal=sig, from_node=from_n, to_node=to_n, method=method))
            continue

        # Check node header
        m_node = node_header_pattern.match(line)
        if m_node:
            name, n_type, parent, instance_id = m_node.groups()
            node_type = n_type or "Instance"
            current_node = SceneNode(
                name=name,
                node_type=node_type,
                parent=parent,
                instance_id=instance_id,
            )
            analysis.nodes.append(current_node)

            # Set root node if it has no parent
            if parent is None and not analysis.root_node_name:
                analysis.root_node_name = name
                analysis.root_node_type = node_type
            continue

        # Check script assignment on current node
        if current_node:
            m_script = script_assign_pattern.search(line)
            if m_script:
                s_id = m_script.group(1)
                current_node.script_id = s_id
                script_info = analysis.ext_resources.get(s_id)
                if script_info:
                    if current_node.parent is None:
                        analysis.attached_script = script_info["path"]

    # Build hierarchy summary string and structured indented tree list
    children_map: Dict[str, List[SceneNode]] = {}
    for n in analysis.nodes:
        p = n.parent or "root"
        children_map.setdefault(p, []).append(n)

    root_nodes = children_map.get("root", [])
    if root_nodes:
        root = root_nodes[0]
        root_line = f"{root.name} ({root.node_type})"
        analysis.hierarchy_tree.append(root_line)

        children = children_map.get(".", [])
        child_names = []
        for c in children:
            child_names.append(f"{c.name} ({c.node_type})")
            if c.instance_id and c.instance_id in analysis.ext_resources:
                inst_res = analysis.ext_resources[c.instance_id].get("path", "")
                analysis.hierarchy_tree.append(f"  {c.name} (instance of {inst_res})")
            else:
                analysis.hierarchy_tree.append(f"  {c.name} ({c.node_type})")

            # Check grandchildren
            sub_children = children_map.get(c.name, [])
            for sc in sub_children:
                analysis.hierarchy_tree.append(f"    {sc.name} ({sc.node_type})")

        if child_names:
            analysis.hierarchy_summary = f"{root.name} ({root.node_type}) -> [{', '.join(child_names)}]"
        else:
            analysis.hierarchy_summary = root_line
    elif analysis.nodes:
        first = analysis.nodes[0]
        first_line = f"{first.name} ({first.node_type})"
        analysis.hierarchy_summary = first_line
        analysis.hierarchy_tree.append(first_line)
    else:
        fallback = f"{analysis.root_node_name or 'Root'} ({analysis.root_node_type or 'Node'})"
        analysis.hierarchy_summary = fallback
        analysis.hierarchy_tree.append(fallback)

    return analysis
