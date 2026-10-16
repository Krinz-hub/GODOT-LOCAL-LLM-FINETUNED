"""Parser and static analyzer for GDScript files."""

from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional


@dataclass
class GDScriptAnalysis:
    class_name: Optional[str] = None
    extends_class: Optional[str] = None
    signals: List[str] = field(default_factory=list)
    signals_emitted: List[str] = field(default_factory=list)
    exported_properties: List[str] = field(default_factory=list)
    variables: List[str] = field(default_factory=list)
    public_methods: List[str] = field(default_factory=list)
    lifecycle_methods: List[str] = field(default_factory=list)
    method_signatures: List[str] = field(default_factory=list)
    preloaded_resources: List[str] = field(default_factory=list)
    lines_of_code: int = 0
    is_tool: bool = False
    has_godot3_syntax: bool = False
    syntax_issues: List[str] = field(default_factory=list)


def parse_gdscript(code: str) -> GDScriptAnalysis:
    """Extracts structural metadata from a GDScript file."""
    analysis = GDScriptAnalysis()
    lines = code.splitlines()
    analysis.lines_of_code = len([l for l in lines if l.strip() and not l.strip().startswith("#")])

    # Regex patterns
    tool_pattern = re.compile(r"^@?tool\b")
    class_name_pattern = re.compile(r"^class_name\s+([A-Za-z0-9_]+)")
    extends_pattern = re.compile(r"^extends\s+([A-Za-z0-9_\".:/]+)")
    signal_pattern = re.compile(r"^signal\s+([A-Za-z0-9_]+)")
    export_pattern = re.compile(r"^@export\s+var\s+([A-Za-z0-9_]+)|^export\s*(?:\([^)]*\))?\s*var\s+([A-Za-z0-9_]+)")
    var_pattern = re.compile(r"^(?:@onready\s+|onready\s+)?var\s+([A-Za-z0-9_]+)")
    func_pattern = re.compile(r"^func\s+([A-Za-z0-9_]+)\s*\((.*?)\)(?:\s*->\s*([A-Za-z0-9_.]+))?:?")
    emit_pattern = re.compile(r"\b([A-Za-z0-9_]+)\.emit\b|emit_signal\s*\(\s*[\"']([A-Za-z0-9_]+)[\"']")
    preload_pattern = re.compile(r'preload\s*\(\s*["\']([^"\']+)["\']\s*\)')

    godot3_export_pattern = re.compile(r"(?<!@)\bexport\s*(?:\([^)]*\))?\s*var\b")
    godot3_onready_pattern = re.compile(r"(?<!@)\bonready\s+var\b")
    godot3_pool_array_pattern = re.compile(r"\bPool[A-Za-z0-9_]*Array\b")

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Tool script check
        if tool_pattern.match(stripped):
            analysis.is_tool = True

        # Class name
        m_cls = class_name_pattern.match(stripped)
        if m_cls:
            analysis.class_name = m_cls.group(1)

        # Extends
        m_ext = extends_pattern.match(stripped)
        if m_ext:
            analysis.extends_class = m_ext.group(1).strip('"\'')

        # Signals
        m_sig = signal_pattern.match(stripped)
        if m_sig:
            analysis.signals.append(m_sig.group(1))

        # Exports
        m_exp = export_pattern.match(stripped)
        if m_exp:
            prop_name = m_exp.group(1) or m_exp.group(2)
            if prop_name:
                analysis.exported_properties.append(prop_name)

        # Variables
        m_var = var_pattern.match(stripped)
        if m_var:
            analysis.variables.append(m_var.group(1))

        # Functions
        m_func = func_pattern.match(stripped)
        if m_func:
            fn_name = m_func.group(1)
            params = m_func.group(2) or ""
            ret_type = m_func.group(3)
            sig = f"{fn_name}({params.strip()})"
            if ret_type:
                sig += f" -> {ret_type.strip()}"
            analysis.method_signatures.append(sig)

            if fn_name.startswith("_"):
                analysis.lifecycle_methods.append(fn_name)
            else:
                analysis.public_methods.append(fn_name)

        # Detect signal emissions
        m_emit = emit_pattern.search(stripped)
        if m_emit:
            sig_name = m_emit.group(1) or m_emit.group(2)
            if sig_name and sig_name not in analysis.signals_emitted:
                analysis.signals_emitted.append(sig_name)

        # Preloaded resources
        for m_pre in preload_pattern.finditer(stripped):
            analysis.preloaded_resources.append(m_pre.group(1))

        # Godot 3 syntax detection
        if godot3_export_pattern.search(stripped):
            analysis.has_godot3_syntax = True
            analysis.syntax_issues.append(f"Legacy Godot 3 export syntax on line: {stripped}")
        if godot3_onready_pattern.search(stripped):
            analysis.has_godot3_syntax = True
            analysis.syntax_issues.append(f"Legacy Godot 3 onready syntax on line: {stripped}")
        if godot3_pool_array_pattern.search(stripped):
            analysis.has_godot3_syntax = True
            analysis.syntax_issues.append(f"Legacy Godot 3 PoolArray syntax on line: {stripped}")

    return analysis
