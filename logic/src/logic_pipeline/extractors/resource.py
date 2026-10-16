"""Parser for Godot .tres text resource files."""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List


@dataclass
class ResourceAnalysis:
    resource_type: str = "Resource"
    format_version: int = 3
    properties: Dict[str, Any] = field(default_factory=dict)
    ext_resources: List[str] = field(default_factory=list)


def parse_resource_file(content: str) -> ResourceAnalysis:
    """Parses a Godot .tres file into structured ResourceAnalysis."""
    analysis = ResourceAnalysis()

    res_header_pattern = re.compile(r'\[gd_resource\s+type="([^"]+)"(?:\s+format=(\d+))?')
    ext_res_pattern = re.compile(r'\[ext_resource\s+type="([^"]+)"\s+(?:uid="[^"]+"\s+)?path="([^"]+)"')

    in_resource_section = False

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue

        m_head = res_header_pattern.match(line)
        if m_head:
            analysis.resource_type = m_head.group(1)
            if m_head.group(2):
                analysis.format_version = int(m_head.group(2))
            continue

        m_ext = ext_res_pattern.match(line)
        if m_ext:
            analysis.ext_resources.append(m_ext.group(2))
            continue

        if line == "[resource]":
            in_resource_section = True
            continue

        if line.startswith("[") and line.endswith("]"):
            in_resource_section = False
            continue

        if in_resource_section and "=" in line:
            k, v = line.split("=", 1)
            analysis.properties[k.strip()] = v.strip().strip('"')

    return analysis
