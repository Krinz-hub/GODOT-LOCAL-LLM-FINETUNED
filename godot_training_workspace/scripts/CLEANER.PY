#!/usr/bin/env python3
"""
Godot Engine ETL Pipeline for Code LLM Fine-Tuning (ShareGPT / ChatML)
=======================================================================
A multi-threaded 4-stage ETL pipeline for cleaning scraped Godot Engine files
and transforming them into high-quality ShareGPT/ChatML .jsonl datasets for
fine-tuning offline Code LLMs (e.g., Qwen2.5-Coder).

Stages:
  Stage 1: Vendor Bloat Purge & Sensitivity Scrub
  Stage 2: Quarantine & Transpilation (Godot 3 -> 4)
  Stage 3: Scene-to-Script Grounding (Hierarchy extraction)
  Stage 4: Formatting & ShareGPT/ChatML Export
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(threadName)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("GodotETL")

# ---------------------------------------------------------------------------
# Constants & Extension Rules
# ---------------------------------------------------------------------------
WHITELIST_EXTENSIONS: Set[str] = {".gd", ".tscn", ".tres"}

VENDOR_BLOAT_EXTENSIONS: Set[str] = {
    ".c", ".h", ".cpp", ".cxx", ".cc", ".hpp",
    ".dll", ".so", ".dylib", ".wasm", ".a", ".lib", ".obj", ".o",
}

GODOT_LIFECYCLE_HOOKS: Set[str] = {
    "_init",
    "_ready",
    "_enter_tree",
    "_exit_tree",
    "_process",
    "_physics_process",
    "_input",
    "_unhandled_input",
    "_unhandled_key_input",
    "_draw",
    "_notification",
    "_gui_input",
}

# ---------------------------------------------------------------------------
# Compiled Regex Patterns (Thread-Safe)
# ---------------------------------------------------------------------------

# Stage 1: Sensitivity Scrub
# Emails: standard RFC 5322 compliant regex
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# Local filesystem paths: Windows drive paths and Unix user paths.
# Explicitly avoids Godot internal resource protocols: res:// and user://,
# as well as Godot scene tree root nodes (/root/...).
LOCAL_PATHS_REGEX = re.compile(
    r"(?:"
    # Windows drive paths: C:/Users/..., C:\Users\..., D:\Projects\...
    r"\b[a-zA-Z]:[/\\](?:Users|Documents|Desktop|Downloads|Projects|workspace|code|home)[/\\][^\s\"'`;>\n\r]+"
    r"|"
    # Unix user paths: /home/user/..., /Users/user/...
    r"(?<![a-zA-Z0-9_])/(?:home|Users|private/var/folders)/[A-Za-z0-9_.-]+(?:/[^\s\"'`;>\n\r]*)?"
    r")"
)

# Stage 1: Binary Bloat (Base64)
# Matches large Base64 blobs (>100 characters) inside strings or raw tokens
BASE64_BLOAT_REGEX = re.compile(
    r'"(?:data:[^;]+;base64,)?[A-Za-z0-9+/=]{100,}"'
)

# Stage 1: Binary Arrays Header Pattern
BINARY_ARRAY_START_REGEX = re.compile(
    r"\b(?:Packed|Pool)[A-Za-z0-9_]*Array\s*\("
)

# Stage 2: Transpilation (Godot 3 -> Godot 4)
# Use negative lookbehind (?<!@) so pre-existing Godot 4 @export / @onready are not doubled to @@
EXPORT_VAR_REGEX = re.compile(r"(?<!@)\bexport\s*(?:\([^)]*\))?\s*var\b")
ONREADY_VAR_REGEX = re.compile(r"(?<!@)\bonready\s+var\b")
KINEMATIC_2D_REGEX = re.compile(r"\bKinematicBody2D\b")
KINEMATIC_3D_REGEX = re.compile(r"\bKinematicBody\b")
INSTANCE_CALL_REGEX = re.compile(r"\.instance\(\s*\)")
YIELD_AWAIT_REGEX = re.compile(
    r"\byield\s*\(\s*([^,]+?)\s*,\s*[\"']([^\"']+)[\"']\s*\)"
)

# Stage 2: Quarantine Rules
SET_PAUSE_MODE_REGEX = re.compile(r"\bset_pause_mode\b")
OS_GET_WINDOW_SIZE_REGEX = re.compile(r"\bOS\.get_window_size\b")

# Stage 3: TSCN Parsing
TSCN_NODE_TAG_REGEX = re.compile(r"\[node\s+([^\]]+)\]")
TSCN_ATTR_NAME_REGEX = re.compile(r'name="([^"]+)"')
TSCN_ATTR_TYPE_REGEX = re.compile(r'type="([^"]+)"')
TSCN_ATTR_PARENT_REGEX = re.compile(r'parent="([^"]+)"')
TSCN_ATTR_INSTANCE_REGEX = re.compile(r'instance=ExtResource\("?([^"\)]+)"?\)')
TSCN_EXT_RESOURCE_REGEX = re.compile(
    r'\[ext_resource\s+[^\]]*path="([^"]+)"[^\]]*id="?([^"\]\s]+)"?'
)


# ---------------------------------------------------------------------------
# Pipeline Statistics Collector (Thread-Safe)
# ---------------------------------------------------------------------------
@dataclass
class PipelineStats:
    lock: threading.Lock = field(default_factory=threading.Lock)
    total_files_scanned: int = 0
    whitelisted_files: int = 0
    vendor_bloat_dropped: int = 0
    vendor_bloat_deleted: int = 0
    other_files_ignored: int = 0
    
    gd_files_scanned: int = 0
    tscn_files_scanned: int = 0
    tres_files_scanned: int = 0
    
    # Sensitivity & Bloat
    emails_redacted: int = 0
    local_paths_redacted: int = 0
    binary_arrays_stripped: int = 0
    base64_blobs_stripped: int = 0
    
    # Transpilation counters
    transpiled_export_var: int = 0
    transpiled_onready_var: int = 0
    transpiled_kinematic_2d: int = 0
    transpiled_kinematic_3d: int = 0
    transpiled_instance_calls: int = 0
    transpiled_yield_await: int = 0
    
    # Quarantine / Drops
    quarantined_untranspilable: int = 0
    quarantined_empty_lifecycle: int = 0
    quarantined_encoding_error: int = 0
    quarantined_no_scene_pair: int = 0
    
    # Final Output
    pairs_processed: int = 0
    records_exported: int = 0
    start_time: float = field(default_factory=time.time)

    def increment(self, attr: str, amount: int = 1) -> None:
        with self.lock:
            setattr(self, attr, getattr(self, attr) + amount)

    def summary(self) -> Dict[str, Any]:
        with self.lock:
            elapsed = time.time() - self.start_time
            return {
                "scan": {
                    "total_files_scanned": self.total_files_scanned,
                    "whitelisted_files": self.whitelisted_files,
                    "vendor_bloat_dropped": self.vendor_bloat_dropped,
                    "vendor_bloat_deleted": self.vendor_bloat_deleted,
                    "other_files_ignored": self.other_files_ignored,
                    "gd_scripts": self.gd_files_scanned,
                    "tscn_scenes": self.tscn_files_scanned,
                    "tres_resources": self.tres_files_scanned,
                },
                "stage_1_sanitization": {
                    "emails_redacted": self.emails_redacted,
                    "local_paths_redacted": self.local_paths_redacted,
                    "binary_arrays_stripped": self.binary_arrays_stripped,
                    "base64_blobs_stripped": self.base64_blobs_stripped,
                },
                "stage_2_transpilation": {
                    "export_var": self.transpiled_export_var,
                    "onready_var": self.transpiled_onready_var,
                    "kinematic_2d": self.transpiled_kinematic_2d,
                    "kinematic_3d": self.transpiled_kinematic_3d,
                    "instance_calls": self.transpiled_instance_calls,
                    "yield_await": self.transpiled_yield_await,
                },
                "quarantine_drops": {
                    "untranspilable_apis": self.quarantined_untranspilable,
                    "empty_lifecycle_stubs": self.quarantined_empty_lifecycle,
                    "encoding_errors": self.quarantined_encoding_error,
                    "unpaired_scripts_skipped": self.quarantined_no_scene_pair,
                },
                "export": {
                    "pairs_processed": self.pairs_processed,
                    "records_exported": self.records_exported,
                    "elapsed_seconds": round(elapsed, 2),
                    "throughput_records_per_sec": round(
                        self.records_exported / elapsed if elapsed > 0 else 0, 2
                    ),
                },
            }


# ---------------------------------------------------------------------------
# Stage 1: Sensitivity Scrub & Binary Bloat Removal
# ---------------------------------------------------------------------------
def scrub_sensitivity(text: str, stats: Optional[PipelineStats] = None) -> str:
    """Removes hardcoded local filesystem paths and redacts emails."""
    # Redact Emails
    def _replace_email(m: re.Match) -> str:
        if stats:
            stats.increment("emails_redacted")
        return "<REDACTED_EMAIL>"

    text = EMAIL_REGEX.sub(_replace_email, text)

    # Redact Local Paths
    def _replace_path(m: re.Match) -> str:
        if stats:
            stats.increment("local_paths_redacted")
        return "<REDACTED_PATH>"

    text = LOCAL_PATHS_REGEX.sub(_replace_path, text)
    return text


def strip_binary_bloat(
    text: str,
    threshold: int = 100,
    stats: Optional[PipelineStats] = None,
) -> str:
    """Replaces massive binary payloads (Packed*Array, Pool*Array > threshold bytes)

    and base64 strings with '/* stripped binary data */'.
    Properly balances nested parentheses and string literals without ReDoS.
    """
    # 1. Base64 Blobs
    def _replace_b64(m: re.Match) -> str:
        if stats:
            stats.increment("base64_blobs_stripped")
        return "/* stripped binary data */"

    text = BASE64_BLOAT_REGEX.sub(_replace_b64, text)

    # 2. Packed and Pool Arrays with threshold check
    result: List[str] = []
    last_idx = 0
    n = len(text)

    for match in BINARY_ARRAY_START_REGEX.finditer(text):
        start_idx = match.start()
        open_paren_idx = match.end() - 1

        if start_idx < last_idx:
            continue

        result.append(text[last_idx:start_idx])

        # Traverse to find matching closing parenthesis
        depth = 1
        i = open_paren_idx + 1
        while i < n and depth > 0:
            ch = text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch in ('"', "'"):
                # Handle quoted strings inside array
                quote = ch
                i += 1
                while i < n and text[i] != quote:
                    if text[i] == "\\":
                        i += 1
                    i += 1
            i += 1

        if depth == 0:
            content = text[open_paren_idx + 1 : i - 1]
            # Check length in bytes
            if len(content.strip().encode("utf-8", errors="ignore")) > threshold:
                result.append("/* stripped binary data */")
                if stats:
                    stats.increment("binary_arrays_stripped")
            else:
                result.append(text[start_idx:i])
            last_idx = i
        else:
            # Reached EOF without matching paren
            result.append(text[start_idx : open_paren_idx + 1])
            last_idx = open_paren_idx + 1

    result.append(text[last_idx:])
    return "".join(result)


# ---------------------------------------------------------------------------
# Stage 2: Quarantine & Transpilation (Godot 3 -> 4)
# ---------------------------------------------------------------------------
def check_quarantine(code: str) -> Optional[str]:
    """Checks whether the GDScript contains APIs that cannot be cleanly transpiled.

    Returns the quarantine reason or None if acceptable.
    """
    if SET_PAUSE_MODE_REGEX.search(code):
        return "contains 'set_pause_mode' (deprecated Godot 3 pause mode API)"
    if OS_GET_WINDOW_SIZE_REGEX.search(code):
        return "contains 'OS.get_window_size' (deprecated Godot 3 window API)"
    return None


def is_empty_or_lifecycle_stub(code: str) -> bool:
    """Checks whether the script consists ONLY of empty lifecycle hooks

    (e.g., 'func _ready(): pass') or comments/boilerplate declarations.
    """
    lines = code.splitlines()
    clean_lines: List[str] = []

    for line in lines:
        # Strip comments
        no_comment = re.sub(r"#.*$", "", line).strip()
        if no_comment:
            clean_lines.append(no_comment)

    # Completely empty or only comments
    if not clean_lines:
        return True

    # Filter out header statements that don't constitute substantive logic
    body_lines: List[str] = []
    for line in clean_lines:
        if line.startswith("extends ") or line.startswith("class_name "):
            continue
        if line in ("@tool", "tool"):
            continue
        if line.startswith("@icon("):
            continue
        body_lines.append(line)

    # If only header statements exist without any variables or functions
    if not body_lines:
        return True

    # Check if all functions are empty lifecycle hooks with ONLY 'pass'
    i = 0
    total_body = len(body_lines)
    while i < total_body:
        line = body_lines[i]

        # Single-line function: func _ready(...): pass
        single_m = re.match(
            r"^func\s+([A-Za-z0-9_]+)\s*\([^)]*\)(?:\s*->\s*[A-Za-z0-9_]+)?\s*:\s*pass;?$",
            line,
        )
        if single_m:
            func_name = single_m.group(1)
            if func_name in GODOT_LIFECYCLE_HOOKS:
                i += 1
                continue
            return False

        # Multi-line function header: func _ready(...):
        multi_m = re.match(
            r"^func\s+([A-Za-z0-9_]+)\s*\([^)]*\)(?:\s*->\s*[A-Za-z0-9_]+)?\s*:$",
            line,
        )
        if multi_m:
            func_name = multi_m.group(1)
            if func_name not in GODOT_LIFECYCLE_HOOKS:
                return False
            # Next line must be pass
            if i + 1 < total_body and body_lines[i + 1] in ("pass", "pass;"):
                i += 2
                continue
            return False

        # Any other line (variables, constants, logic, custom functions)
        return False

    return True


def transpile_gdscript(
    code: str,
    stats: Optional[PipelineStats] = None,
) -> str:
    """Applies modernizing transpilation rules from Godot 3 to Godot 4."""
    # 1. export var -> @export var
    if stats:
        matches = len(EXPORT_VAR_REGEX.findall(code))
        if matches:
            stats.increment("transpiled_export_var", matches)
    code = EXPORT_VAR_REGEX.sub("@export var", code)

    # 2. onready var -> @onready var
    if stats:
        matches = len(ONREADY_VAR_REGEX.findall(code))
        if matches:
            stats.increment("transpiled_onready_var", matches)
    code = ONREADY_VAR_REGEX.sub("@onready var", code)

    # 3. KinematicBody2D -> CharacterBody2D
    if stats:
        matches = len(KINEMATIC_2D_REGEX.findall(code))
        if matches:
            stats.increment("transpiled_kinematic_2d", matches)
    code = KINEMATIC_2D_REGEX.sub("CharacterBody2D", code)

    # 4. KinematicBody -> CharacterBody3D (KinematicBody2D already transformed)
    if stats:
        matches = len(KINEMATIC_3D_REGEX.findall(code))
        if matches:
            stats.increment("transpiled_kinematic_3d", matches)
    code = KINEMATIC_3D_REGEX.sub("CharacterBody3D", code)

    # 5. .instance() -> .instantiate()
    if stats:
        matches = len(INSTANCE_CALL_REGEX.findall(code))
        if matches:
            stats.increment("transpiled_instance_calls", matches)
    code = INSTANCE_CALL_REGEX.sub(".instantiate()", code)

    # 6. yield(target, "signal") -> await target.signal
    if stats:
        matches = len(YIELD_AWAIT_REGEX.findall(code))
        if matches:
            stats.increment("transpiled_yield_await", matches)
    code = YIELD_AWAIT_REGEX.sub(r"await \1.\2", code)

    return code


# ---------------------------------------------------------------------------
# Stage 3: Scene-to-Script Grounding (TSCN Parsing & Tree Construction)
# ---------------------------------------------------------------------------
class SceneNode:
    """Represents a node inside a Godot .tscn scene tree hierarchy."""

    def __init__(self, name: str, node_type: str = ""):
        self.name = name
        self.node_type = node_type
        self.children: List["SceneNode"] = []


# Mapping Godot 3 node types to Godot 4
TSC_TYPE_MIGRATIONS = {
    "KinematicBody2D": "CharacterBody2D",
    "KinematicBody": "CharacterBody3D",
    "Spatial": "Node3D",
    "Position2D": "Marker2D",
    "Position3D": "Marker3D",
}


def parse_tscn_scene_tree(tscn_content: str) -> str:
    """Parses a Godot .tscn file content and extracts the node hierarchy.

    Returns a formatted string representing the scene tree:
    e.g. 'Scene Tree: Root (Node2D) -> Player (CharacterBody2D) -> CollisionShape2D'
    """
    # Parse external resources to resolve scene instances if type is omitted
    ext_resources: Dict[str, str] = {}
    for ext_match in TSCN_EXT_RESOURCE_REGEX.finditer(tscn_content):
        res_path = ext_match.group(1)
        res_id = ext_match.group(2)
        scene_name = Path(res_path).stem
        ext_resources[res_id] = scene_name

    root: Optional[SceneNode] = None
    node_map: Dict[str, SceneNode] = {}

    for match in TSCN_NODE_TAG_REGEX.finditer(tscn_content):
        attrs = match.group(1)

        name_m = TSCN_ATTR_NAME_REGEX.search(attrs)
        if not name_m:
            continue
        name = name_m.group(1)

        type_m = TSCN_ATTR_TYPE_REGEX.search(attrs)
        node_type = type_m.group(1) if type_m else ""

        # If type is omitted, check if it is an instance of an external scene
        if not node_type:
            inst_m = TSCN_ATTR_INSTANCE_REGEX.search(attrs)
            if inst_m:
                inst_id = inst_m.group(1)
                node_type = ext_resources.get(inst_id, "")

        # Modernize type names for Godot 4
        node_type = TSC_TYPE_MIGRATIONS.get(node_type, node_type)

        parent_m = TSCN_ATTR_PARENT_REGEX.search(attrs)
        parent_path = parent_m.group(1) if parent_m else None

        node = SceneNode(name=name, node_type=node_type)

        if root is None or parent_path is None:
            # Root node
            root = node
            node_map["."] = node
            node_map[name] = node
        else:
            # Child node
            parent_node = node_map.get(parent_path)
            if not parent_node:
                # Fallback to tail name or root if path is relative
                tail = parent_path.split("/")[-1]
                parent_node = node_map.get(tail, root)

            parent_node.children.append(node)

            # Register path in lookup table
            if parent_path == ".":
                node_map[name] = node
            else:
                node_map[f"{parent_path}/{name}"] = node
                node_map[name] = node

    if not root:
        return "Scene Tree: Root (Node)"

    def _format_label(n: SceneNode) -> str:
        if n.node_type and n.node_type != n.name:
            return f"{n.name} ({n.node_type})"
        return n.name

    def _format_subtree(n: SceneNode) -> str:
        label = _format_label(n)
        if not n.children:
            return label
        if len(n.children) == 1:
            return f"{label} -> {_format_subtree(n.children[0])}"
        child_strs = [_format_subtree(c) for c in n.children]
        return f"{label} -> [{', '.join(child_strs)}]"

    return f"Scene Tree: {_format_subtree(root)}"


# ---------------------------------------------------------------------------
# Stage 4: Formatting & ShareGPT/ChatML Export
# ---------------------------------------------------------------------------
def format_sharegpt_record(
    filename: str,
    scene_tree_string: str,
    cleaned_code: str,
) -> Dict[str, Any]:
    """Formats the cleaned GDScript and Scene Tree into standard ShareGPT/ChatML

    structure for LLM instruction fine-tuning.
    """
    return {
        "messages": [
            {
                "role": "system",
                "content": "You are an expert Godot 4 Engine developer and autonomous AI agent.",
            },
            {
                "role": "user",
                "content": f"Given this scene tree:\n{scene_tree_string}\n\nWrite the GDScript implementation for {filename}.",
            },
            {
                "role": "assistant",
                "content": f"```gdscript\n{cleaned_code.strip()}\n```",
            },
        ]
    }


# ---------------------------------------------------------------------------
# ETL Pipeline Engine
# ---------------------------------------------------------------------------
@dataclass
class ETLConfig:
    input_dir: Path
    output_file: Path
    quarantine_file: Optional[Path] = None
    stats_file: Optional[Path] = None
    workers: int = 8
    require_scene_pair: bool = True
    dry_run: bool = False
    bloat_byte_threshold: int = 100
    delete_unwanted: bool = False


class GodotETLPipeline:
    """Multi-threaded ETL Pipeline orchestrating Stages 1 through 4."""

    def __init__(self, config: ETLConfig):
        self.config = config
        self.stats = PipelineStats()
        self._output_lock = threading.Lock()
        self._quarantine_lock = threading.Lock()
        self._output_handle = None
        self._quarantine_handle = None

    def scan_directory(self) -> Tuple[List[Path], Dict[str, Path]]:
        """Recursively scans input directory, applies whitelist/vendor filters,

        and builds a pairing registry between .gd and .tscn files.
        """
        logger.info(f"Scanning input directory: {self.config.input_dir}...")
        gd_files: List[Path] = []
        tscn_files: Dict[str, Path] = {}

        for root, _, files in os.walk(self.config.input_dir):
            for filename in files:
                self.stats.increment("total_files_scanned")
                file_path = Path(root) / filename
                suffix = file_path.suffix.lower()

                # Check vendor bloat first
                if suffix in VENDOR_BLOAT_EXTENSIONS:
                    self.stats.increment("vendor_bloat_dropped")
                    if self.config.delete_unwanted and not self.config.dry_run:
                        try:
                            file_path.unlink()
                            self.stats.increment("vendor_bloat_deleted")
                        except Exception as e:
                            logger.warning(f"Could not delete {file_path}: {e}")
                    continue

                # Check whitelist
                if suffix not in WHITELIST_EXTENSIONS:
                    self.stats.increment("other_files_ignored")
                    continue

                self.stats.increment("whitelisted_files")

                if suffix == ".gd":
                    self.stats.increment("gd_files_scanned")
                    gd_files.append(file_path)
                elif suffix == ".tscn":
                    self.stats.increment("tscn_files_scanned")
                    # Key by directory and lowercase stem for case-insensitive pairing
                    key = f"{file_path.parent.resolve()}/{file_path.stem.lower()}"
                    tscn_files[key] = file_path
                elif suffix == ".tres":
                    self.stats.increment("tres_files_scanned")

        logger.info(
            f"Scan complete. Whitelisted files: {self.stats.whitelisted_files} "
            f"({len(gd_files)} .gd scripts, {len(tscn_files)} .tscn scenes). "
            f"Dropped {self.stats.vendor_bloat_dropped} vendor bloat files."
        )
        return gd_files, tscn_files

    def _process_single_gd(
        self,
        gd_path: Path,
        matching_tscn_path: Optional[Path],
    ) -> Optional[Dict[str, Any]]:
        """Executes Stages 1-4 for a single .gd script and its matching scene."""
        try:
            with open(gd_path, "r", encoding="utf-8", errors="replace") as f:
                gd_raw = f.read()
        except Exception as e:
            self.stats.increment("quarantined_encoding_error")
            self._write_quarantine(gd_path, f"Read error: {e}")
            return None

        # Stage 1: Sensitivity Scrub on GDScript
        gd_scrubbed = scrub_sensitivity(gd_raw, self.stats)

        # Stage 2: Quarantine Checks
        quarantine_reason = check_quarantine(gd_scrubbed)
        if quarantine_reason:
            self.stats.increment("quarantined_untranspilable")
            self._write_quarantine(gd_path, quarantine_reason)
            return None

        if is_empty_or_lifecycle_stub(gd_scrubbed):
            self.stats.increment("quarantined_empty_lifecycle")
            self._write_quarantine(gd_path, "Consists only of empty lifecycle hooks/stubs")
            return None

        # Stage 2: Transpilation (Godot 3 -> 4)
        gd_cleaned = transpile_gdscript(gd_scrubbed, self.stats)

        # Verify that transpilation didn't reduce it to an empty stub
        if is_empty_or_lifecycle_stub(gd_cleaned):
            self.stats.increment("quarantined_empty_lifecycle")
            self._write_quarantine(gd_path, "Became empty lifecycle stub after transpilation")
            return None

        # Stage 3: Scene-to-Script Grounding
        scene_tree_string: str = ""
        if matching_tscn_path and matching_tscn_path.is_file():
            try:
                with open(matching_tscn_path, "r", encoding="utf-8", errors="replace") as f:
                    tscn_raw = f.read()
                # Stage 1 on .tscn: Sensitivity Scrub + Binary Bloat Removal
                tscn_scrubbed = scrub_sensitivity(tscn_raw, self.stats)
                tscn_clean = strip_binary_bloat(
                    tscn_scrubbed,
                    threshold=self.config.bloat_byte_threshold,
                    stats=self.stats,
                )
                scene_tree_string = parse_tscn_scene_tree(tscn_clean)
            except Exception as e:
                logger.warning(f"Error parsing .tscn {matching_tscn_path}: {e}")
                scene_tree_string = f"Scene Tree: Root (Node) [Parse Error: {matching_tscn_path.stem}]"
        else:
            if self.config.require_scene_pair:
                self.stats.increment("quarantined_no_scene_pair")
                self._write_quarantine(gd_path, "No matching .tscn scene file in directory")
                return None
            else:
                scene_tree_string = f"Scene Tree: {gd_path.stem} (Standalone GDScript)"

        # Stage 4: Formatting
        record = format_sharegpt_record(
            filename=gd_path.name,
            scene_tree_string=scene_tree_string,
            cleaned_code=gd_cleaned,
        )

        self.stats.increment("pairs_processed")
        return record

    def _write_record(self, record: Dict[str, Any]) -> None:
        if self.config.dry_run or not self._output_handle:
            return
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._output_lock:
            self._output_handle.write(line)
        self.stats.increment("records_exported")

    def _write_quarantine(self, path: Path, reason: str) -> None:
        if self.config.dry_run or not self._quarantine_handle:
            return
        entry = {
            "path": str(path),
            "reason": reason,
            "timestamp": time.time(),
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._quarantine_lock:
            self._quarantine_handle.write(line)

    def run(self) -> Dict[str, Any]:
        """Executes the complete multi-threaded pipeline."""
        start_time = time.time()
        gd_files, tscn_files = self.scan_directory()

        # Prepare outputs
        if not self.config.dry_run:
            self.config.output_file.parent.mkdir(parents=True, exist_ok=True)
            self._output_handle = open(self.config.output_file, "w", encoding="utf-8")
            if self.config.quarantine_file:
                self.config.quarantine_file.parent.mkdir(parents=True, exist_ok=True)
                self._quarantine_handle = open(
                    self.config.quarantine_file, "w", encoding="utf-8"
                )

        logger.info(
            f"Launching multi-threaded processing with {self.config.workers} worker threads..."
        )

        try:
            with ThreadPoolExecutor(
                max_workers=self.config.workers,
                thread_name_prefix="ETLWorker",
            ) as executor:
                futures = {}
                for gd_path in gd_files:
                    key = f"{gd_path.parent.resolve()}/{gd_path.stem.lower()}"
                    matching_tscn = tscn_files.get(key)
                    fut = executor.submit(
                        self._process_single_gd, gd_path, matching_tscn
                    )
                    futures[fut] = gd_path

                processed_count = 0
                total_to_process = len(futures)
                for fut in as_completed(futures):
                    processed_count += 1
                    try:
                        record = fut.result()
                        if record:
                            self._write_record(record)
                    except Exception as exc:
                        gd_p = futures[fut]
                        logger.error(f"Worker exception processing {gd_p}: {exc}")

                    if processed_count % 1000 == 0 or processed_count == total_to_process:
                        logger.info(
                            f"Progress: {processed_count}/{total_to_process} scripts "
                            f"({(processed_count / total_to_process) * 100:.1f}%) | "
                            f"Exported: {self.stats.records_exported}"
                        )
        finally:
            if self._output_handle:
                self._output_handle.close()
            if self._quarantine_handle:
                self._quarantine_handle.close()

        summary_data = self.stats.summary()
        logger.info(f"Pipeline finished in {time.time() - start_time:.2f} seconds.")

        if self.config.stats_file:
            self.config.stats_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config.stats_file, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2)
            logger.info(f"Statistics written to {self.config.stats_file}")

        return summary_data


# ---------------------------------------------------------------------------
# CLI Argument Parser & Entry Point
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Multi-threaded Godot Engine ETL Pipeline for ShareGPT/ChatML LLM Fine-Tuning.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input-dir", "-i",
        type=Path,
        default=Path("."),
        help="Root directory of raw Godot engine files to process.",
    )
    parser.add_argument(
        "--output-file", "-o",
        type=Path,
        default=Path("godot_sharegpt.jsonl"),
        help="Path for exported ShareGPT/ChatML .jsonl file.",
    )
    parser.add_argument(
        "--quarantine-file", "-q",
        type=Path,
        default=Path("quarantine_records.jsonl"),
        help="Path for logging dropped/quarantined files with reasons.",
    )
    parser.add_argument(
        "--stats-file", "-s",
        type=Path,
        default=None,
        help="Optional path to output execution statistics JSON.",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=min(32, (os.cpu_count() or 4) * 4),
        help="Number of worker threads for parallel ETL processing.",
    )
    parser.add_argument(
        "--allow-standalone",
        action="store_true",
        help="If set, exports .gd scripts even if no matching .tscn scene file is found in directory.",
    )
    parser.add_argument(
        "--bloat-threshold",
        type=int,
        default=100,
        help="Byte length threshold above which Packed/Pool arrays are stripped from scenes/resources.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and transform data in-memory without writing to output files.",
    )
    parser.add_argument(
        "--delete-unwanted",
        action="store_true",
        help="Physically delete unwanted vendor bloat files (.c, .h, .cpp, .dll, .wasm, etc.) from disk in the input directory.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the internal verification test suite covering Stages 1 to 4.",
    )
    return parser


# ---------------------------------------------------------------------------
# Self-Test Suite (Verification)
# ---------------------------------------------------------------------------
def run_self_test() -> int:
    """Executes unit tests verifying Stages 1 through 4."""
    import unittest

    class TestGodotETL(unittest.TestCase):
        def test_stage_1_sensitivity_and_bloat(self):
            # Email and path scrub
            sample_code = (
                "# Author: john.doe@example.com\n"
                "var cache_path = 'C:/Users/Administrator/AppData/save.dat'\n"
                "var unix_path = '/home/piet/project/config.json'\n"
                "var godot_res = 'res://scenes/Player.tscn'\n"
                "var godot_user = 'user://data.bin'\n"
            )
            scrubbed = scrub_sensitivity(sample_code)
            self.assertIn("<REDACTED_EMAIL>", scrubbed)
            self.assertNotIn("john.doe@example.com", scrubbed)
            self.assertIn("<REDACTED_PATH>", scrubbed)
            self.assertNotIn("Administrator", scrubbed)
            self.assertNotIn("/home/piet", scrubbed)
            # Ensure Godot paths were NOT scrubbed
            self.assertIn("res://scenes/Player.tscn", scrubbed)
            self.assertIn("user://data.bin", scrubbed)

            # Binary bloat removal on .tscn
            small_arr = "PackedFloat32Array(1.0, 2.0)"
            large_arr = "PackedFloat32Array(" + ", ".join(["1.0"] * 60) + ")"
            base64_blob = '"' + "A" * 120 + '"'
            tscn_sample = f"mesh_small = {small_arr}\nmesh_large = {large_arr}\nraw_tex = {base64_blob}"

            cleaned = strip_binary_bloat(tscn_sample, threshold=100)
            self.assertIn("PackedFloat32Array(1.0, 2.0)", cleaned)
            self.assertIn("/* stripped binary data */", cleaned)
            self.assertNotIn(large_arr, cleaned)
            self.assertNotIn(base64_blob, cleaned)

        def test_stage_2_transpilation(self):
            g3_script = (
                "extends KinematicBody2D\n"
                "export(int) var speed = 200\n"
                "export (float, 0, 100) var hp = 50.0\n"
                "onready var anim = $AnimationPlayer\n"
                "var enemy: KinematicBody\n"
                "func _ready():\n"
                "    var bullet = bullet_scene.instance()\n"
                '    yield(get_tree(), "idle_frame")\n'
                '    yield(timer, "timeout")\n'
            )
            g4_script = transpile_gdscript(g3_script)
            self.assertIn("extends CharacterBody2D", g4_script)
            self.assertIn("@export var speed = 200", g4_script)
            self.assertIn("@export var hp = 50.0", g4_script)
            self.assertIn("@onready var anim = $AnimationPlayer", g4_script)
            self.assertIn("var enemy: CharacterBody3D", g4_script)
            self.assertIn("bullet_scene.instantiate()", g4_script)
            self.assertIn("await get_tree().idle_frame", g4_script)
            self.assertIn("await timer.timeout", g4_script)

        def test_stage_2_quarantine_drops(self):
            self.assertIsNotNone(check_quarantine("set_pause_mode(PAUSE_MODE_PROCESS)"))
            self.assertIsNotNone(check_quarantine("var size = OS.get_window_size()"))
            self.assertIsNone(check_quarantine("var size = DisplayServer.window_get_size()"))

            # Empty lifecycle hook stubs
            self.assertTrue(is_empty_or_lifecycle_stub("func _ready(): pass"))
            self.assertTrue(is_empty_or_lifecycle_stub("extends Node2D\nfunc _ready():\n    pass"))
            self.assertTrue(
                is_empty_or_lifecycle_stub(
                    "extends CharacterBody2D\n"
                    "func _ready():\n    pass\n"
                    "func _process(delta):\n    pass"
                )
            )
            # Meaningful code should NOT be dropped
            self.assertFalse(
                is_empty_or_lifecycle_stub(
                    "extends CharacterBody2D\n"
                    "var speed = 100\n"
                    "func _physics_process(delta):\n"
                    "    move_and_slide()\n"
                )
            )

        def test_stage_3_scene_tree_parsing(self):
            tscn_sample = (
                '[gd_scene load_steps=2 format=3]\n'
                '[node name="Root" type="Node2D"]\n'
                '[node name="Player" type="KinematicBody2D" parent="."]\n'
                '[node name="CollisionShape2D" type="CollisionShape2D" parent="Player"]\n'
            )
            tree_str = parse_tscn_scene_tree(tscn_sample)
            expected = "Scene Tree: Root (Node2D) -> Player (CharacterBody2D) -> CollisionShape2D"
            self.assertEqual(tree_str, expected)

        def test_stage_4_sharegpt_format(self):
            rec = format_sharegpt_record(
                filename="Player.gd",
                scene_tree_string="Scene Tree: Root (Node2D) -> Player (CharacterBody2D) -> CollisionShape2D",
                cleaned_code="extends CharacterBody2D\n@export var speed = 200",
            )
            messages = rec["messages"]
            self.assertEqual(len(messages), 3)
            self.assertEqual(messages[0]["role"], "system")
            self.assertEqual(
                messages[0]["content"],
                "You are an expert Godot 4 Engine developer and autonomous AI agent.",
            )
            self.assertEqual(messages[1]["role"], "user")
            self.assertIn("Given this scene tree:", messages[1]["content"])
            self.assertIn("Write the GDScript implementation for Player.gd.", messages[1]["content"])
            self.assertEqual(messages[2]["role"], "assistant")
            self.assertTrue(messages[2]["content"].startswith("```gdscript\n"))
            self.assertTrue(messages[2]["content"].endswith("\n```"))

    suite = unittest.TestLoader().loadTestsFromTestCase(TestGodotETL)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    config = ETLConfig(
        input_dir=args.input_dir,
        output_file=args.output_file,
        quarantine_file=args.quarantine_file,
        stats_file=args.stats_file,
        workers=args.workers,
        require_scene_pair=not args.allow_standalone,
        dry_run=args.dry_run,
        bloat_byte_threshold=args.bloat_threshold,
        delete_unwanted=args.delete_unwanted,
    )

    pipeline = GodotETLPipeline(config)
    summary = pipeline.run()
    print("\n" + "=" * 60)
    print("ETL PIPELINE SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
