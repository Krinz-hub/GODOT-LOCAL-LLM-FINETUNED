"""Godot Local AI Agent Server.

Provides REST API endpoints and structured schemas for Godot 4 applications
and editor integrations to interact with the fine-tuned Qwen2.5-Coder model.
"""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
from typing import Any, Dict, List, Optional
import urllib.parse

REPO_ROOT = Path(__file__).resolve().parent
BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
ADAPTER_PATH = str(REPO_ROOT / "godot-agent-lora" / "final_adapter")
SCHEMA_PATH = REPO_ROOT / "logic" / "schemas" / "godot_action.schema.json"

SYSTEM_ACTION_PROMPT = """You are an autonomous Godot 4 AI agent.
Your mission is to plan, generate, inspect, and repair Godot 4 projects.
You MUST output your response as a single, valid JSON object matching the GodotAgentAction schema:

{
  "thought": "Brief explanation of your plan or reasoning",
  "action_type": "create_scene" | "edit_scene" | "delete_scene" | "create_or_update_script" | "create_or_update_scene" | "read_file" | "list_project_files" | "run_project" | "chat_response",
  "parameters": {
    "file_path": "scenes/player.tscn",
    "root_node_name": "Player",
    "root_node_type": "CharacterBody2D",
    "content": "Full Godot 4 GDScript code or TSCN definition without markdown wrappers",
    "command": "--headless --path .",
    "message": "Conversational explanation for chat_response"
  }
}

Rules:
1. Always use modern Godot 4 GDScript (e.g. CharacterBody2D, Vector2.ZERO, typed variables, @export, @onready).
2. For scene actions, specify relative .tscn paths (e.g. 'scenes/level.tscn').
3. Output ONLY the JSON object. Do not wrap in markdown code blocks and do not add text outside the JSON.
"""

# Global references
MODEL: Any = None
TOKENIZER: Any = None
PAD_TOKEN_ID: Optional[int] = None
EOS_TOKEN_ID: Optional[int] = None
DEVICE: str = "cpu"
MODEL_LOCK = threading.Lock()
SESSIONS: Dict[str, List[Dict[str, str]]] = {}
SESSIONS_LOCK = threading.Lock()
DEFAULT_PROJECT_PATH: Optional[str] = os.environ.get("GODOT_PROJECT_PATH")


def load_model_and_tokenizer(device_map: str = "auto") -> None:
    """Loads base model in 4-bit and attaches fine-tuned Godot LoRA adapter."""
    global MODEL, TOKENIZER, PAD_TOKEN_ID, EOS_TOKEN_ID, DEVICE
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        PreTrainedTokenizerBase,
    )
    from peft import PeftModel

    print(f"Loading tokenizer from {ADAPTER_PATH}...")
    tok = AutoTokenizer.from_pretrained(ADAPTER_PATH)
    if not isinstance(tok, PreTrainedTokenizerBase):
        raise RuntimeError("Failed to load a valid tokenizer.")
    TOKENIZER = tok

    print("Loading base model in 4-bit...")
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=quant_config,
        dtype=torch.bfloat16,
        device_map=device_map,
    )

    print("Attaching Godot LoRA adapter...")
    model = PeftModel.from_pretrained(base, ADAPTER_PATH)
    model.eval()
    MODEL = model

    # Resolve EOS and pad tokens
    eos = TOKENIZER.eos_token_id
    if eos is None:
        gen_config = getattr(model, "generation_config", None)
        if gen_config is not None and getattr(gen_config, "eos_token_id", None) is not None:
            cfg_eos = gen_config.eos_token_id
            eos = cfg_eos[0] if isinstance(cfg_eos, list) else int(cfg_eos)
        else:
            eos = 151645
    EOS_TOKEN_ID = eos
    PAD_TOKEN_ID = TOKENIZER.pad_token_id if TOKENIZER.pad_token_id is not None else eos

    DEVICE = str(model.get_input_embeddings().weight.device)
    print(f"Model and adapter successfully loaded on device: {DEVICE}")


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """Robustly extracts JSON object or delimited action from model output."""
    cleaned = text.strip()

    # 0. Check for <godot_action> delimited block with optional adjoining code fence
    delim_match = re.search(r"<godot_action>(.*?)</godot_action>", cleaned, re.DOTALL | re.IGNORECASE)
    if delim_match:
        action_json_str = delim_match.group(1).strip()
        try:
            data = json.loads(action_json_str)
            if isinstance(data, dict):
                code_match = re.search(r"```(?:gdscript|tscn)?\s*\n(.*?)```", cleaned, re.DOTALL)
                if code_match:
                    params = data.setdefault("parameters", {})
                    if not params.get("content"):
                        params["content"] = code_match.group(1).strip()
                return data
        except Exception:
            pass

    # Check for markdown code fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    else:
        # Match outermost curly braces
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]

    # 1. Try strict parsing
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            # If content is empty but an unescaped gdscript fence exists outside the JSON
            if "parameters" in data and not data["parameters"].get("content"):
                code_match = re.search(r"```(?:gdscript|tscn)?\s*\n(.*?)```", text, re.DOTALL)
                if code_match:
                    data["parameters"]["content"] = code_match.group(1).strip()
            return data
    except Exception:
        pass

    # 2. Try non-strict parsing (allows literal unescaped newlines/tabs in GDScript code)
    try:
        data = json.loads(cleaned, strict=False)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 3. Regex extraction fallback for malformed or truncated JSON strings
    act_type = re.search(r'"action_type"\s*:\s*"([^"]+)"', cleaned)
    fp = re.search(r'"file_path"\s*:\s*"([^"]+)"', cleaned)
    if act_type and fp:
        cont_match = re.search(r'"content"\s*:\s*"(.*?)(?:"\s*\}|"\s*,\s*"|$)', cleaned, re.DOTALL)
        content = cont_match.group(1) if cont_match else ""
        content = content.encode().decode("unicode_escape", errors="ignore")
        return {
            "thought": "Recovered action from model JSON output",
            "action_type": act_type.group(1),
            "parameters": {
                "file_path": fp.group(1),
                "content": content,
            },
        }

    # Fallback to chat response if parsing fails
    return {
        "thought": "Failed to parse pure JSON from model output.",
        "action_type": "chat_response",
        "parameters": {"message": text.strip()},
    }


def generate_text(
    messages: List[Dict[str, str]],
    max_new_tokens: int = 1000,
    temperature: float = 0.4,
    do_sample: bool = True,
) -> str:
    """Thread-safe generation using loaded model."""
    import torch
    from transformers import BatchEncoding

    if MODEL is None or TOKENIZER is None:
        return json.dumps({
            "thought": "Mock mode: Model is not loaded.",
            "action_type": "chat_response",
            "parameters": {"message": "Server running in mock mode. Start with active model for inference."},
        })

    with MODEL_LOCK:
        raw_inputs = TOKENIZER.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        )

        input_device = getattr(MODEL, "device", torch.device(DEVICE))
        if isinstance(raw_inputs, BatchEncoding):
            inputs: BatchEncoding = raw_inputs.to(input_device)
        else:
            inputs = BatchEncoding({
                k: v.to(input_device) if isinstance(v, torch.Tensor) else v
                for k, v in raw_inputs.items()
            })

        input_len = inputs["input_ids"].shape[-1]

        with torch.inference_mode():
            outputs = MODEL.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=do_sample,
                temperature=temperature if do_sample else 1.0,
                repetition_penalty=1.05,
                pad_token_id=PAD_TOKEN_ID,
                eos_token_id=EOS_TOKEN_ID,
            )

        new_tokens = outputs[0, input_len:]
        raw_answer = TOKENIZER.decode(new_tokens, skip_special_tokens=True)
        return raw_answer[0].strip() if isinstance(raw_answer, list) else raw_answer.strip()


def sanitize_project_path(project_path: str, relative_file: str) -> Path:
    """Prevents directory traversal attacks outside the project directory."""
    base = Path(project_path).resolve()
    target = (base / relative_file).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError(f"Path traversal detected: {relative_file} resolves outside {base}")
    return target


def detect_godot_format_version(project_path: str) -> int:
    """Detects whether project is Godot 3 (format=2) or Godot 4 (format=3)."""
    try:
        p_file = Path(project_path) / "project.godot"
        if p_file.exists():
            text = p_file.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                if line.strip().startswith("config_version="):
                    val = line.split("=")[-1].strip()
                    if val == "4":
                        return 2  # Godot 3.x
                    elif val == "5":
                        return 3  # Godot 4.x
    except Exception:
        pass
    return 3


def build_scene_content(
    root_node_name: str = "Node2D",
    root_node_type: str = "Node2D",
    script_path: Optional[str] = None,
    nodes: Optional[List[Dict[str, Any]]] = None,
    format_version: int = 3,
) -> str:
    """Constructs a valid Godot .tscn text scene string."""
    lines: List[str] = []
    load_steps = 1
    ext_resources: List[str] = []

    if script_path:
        load_steps += 1
        script_res_id = "1_script"
        clean_script = script_path if script_path.startswith("res://") else f"res://{script_path.lstrip('/')}"
        ext_resources.append(f'[ext_resource type="Script" path="{clean_script}" id="{script_res_id}"]')
    else:
        script_res_id = None

    if nodes:
        for idx, nd in enumerate(nodes, start=2):
            inst = nd.get("instance")
            sc = nd.get("script")
            if inst:
                load_steps += 1
                clean_inst = inst if inst.startswith("res://") else f"res://{inst.lstrip('/')}"
                ext_resources.append(f'[ext_resource type="PackedScene" path="{clean_inst}" id="{idx}_inst"]')
            if sc:
                load_steps += 1
                clean_sc = sc if sc.startswith("res://") else f"res://{sc.lstrip('/')}"
                ext_resources.append(f'[ext_resource type="Script" path="{clean_sc}" id="{idx}_sc"]')

    if load_steps > 1:
        lines.append(f"[gd_scene load_steps={load_steps} format={format_version}]")
    else:
        lines.append(f"[gd_scene format={format_version}]")
    lines.append("")

    for ext in ext_resources:
        lines.append(ext)
    if ext_resources:
        lines.append("")

    lines.append(f'[node name="{root_node_name}" type="{root_node_type}"]')
    if script_res_id:
        lines.append(f'script = ExtResource("{script_res_id}")')
    lines.append("")

    if nodes:
        for idx, nd in enumerate(nodes, start=2):
            name = nd.get("name", f"Node_{idx}")
            parent = nd.get("parent", ".")
            node_type = nd.get("type", "Node")
            inst = nd.get("instance")
            sc = nd.get("script")

            if inst:
                lines.append(f'[node name="{name}" parent="{parent}" instance=ExtResource("{idx}_inst")]')
            else:
                lines.append(f'[node name="{name}" type="{node_type}" parent="{parent}"]')

            if sc:
                lines.append(f'script = ExtResource("{idx}_sc")')

            props = nd.get("properties", {})
            for pk, pv in props.items():
                lines.append(f"{pk} = {pv}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def apply_scene_modifications(
    content: str,
    add_nodes: Optional[List[Dict[str, Any]]] = None,
    remove_nodes: Optional[List[str]] = None,
    attach_script: Optional[Dict[str, str]] = None,
) -> str:
    """Applies structured additions, removals, and script attachments to a .tscn scene."""
    sections: List[tuple[str, List[str]]] = []
    current_header = ""
    current_lines: List[str] = []
    for line in content.splitlines():
        if line.startswith("[") and line.endswith("]"):
            if current_header or current_lines:
                sections.append((current_header, current_lines))
            current_header = line
            current_lines = []
        else:
            current_lines.append(line)
    if current_header or current_lines:
        sections.append((current_header, current_lines))

    # 1. Handle remove_nodes
    if remove_nodes:
        to_remove = set(remove_nodes)
        filtered: List[tuple[str, List[str]]] = []
        for hdr, lns in sections:
            if hdr.startswith("[node "):
                m_name = re.search(r'name="([^"]+)"', hdr)
                m_parent = re.search(r'parent="([^"]+)"', hdr)
                node_name = m_name.group(1) if m_name else ""
                parent_name = m_parent.group(1) if m_parent else ""
                if node_name in to_remove or parent_name in to_remove:
                    to_remove.add(node_name)
                    continue
            filtered.append((hdr, lns))
        sections = filtered

    # Collect existing ext_resources to avoid duplicate IDs
    existing_ext_paths: Dict[str, str] = {}
    max_id = 0
    for hdr, _ in sections:
        if hdr.startswith("[ext_resource "):
            m_path = re.search(r'path="([^"]+)"', hdr)
            m_id = re.search(r'id="([^"]+)"', hdr)
            if m_path and m_id:
                existing_ext_paths[m_path.group(1)] = m_id.group(1)
                num_m = re.match(r"^(\d+)", m_id.group(1))
                if num_m:
                    max_id = max(max_id, int(num_m.group(1)))

    def get_or_create_ext_resource(res_path: str, res_type: str) -> str:
        nonlocal max_id
        clean_path = res_path if res_path.startswith("res://") else f"res://{res_path.lstrip('/')}"
        if clean_path in existing_ext_paths:
            return existing_ext_paths[clean_path]
        max_id += 1
        clean_name = clean_path.split("/")[-1].replace(".", "_")
        new_id = f"{max_id}_{clean_name}"
        existing_ext_paths[clean_path] = new_id
        insert_idx = 1
        for i, (hdr, _) in enumerate(sections):
            if hdr.startswith("[ext_resource ") or hdr.startswith("[gd_scene "):
                insert_idx = i + 1
        sections.insert(insert_idx, (f'[ext_resource type="{res_type}" path="{clean_path}" id="{new_id}"]', [""]))
        return new_id

    # 2. Handle attach_script
    if attach_script:
        target_node = attach_script.get("node", ".")
        script_path = attach_script.get("script_path", "")
        if script_path:
            sc_id = get_or_create_ext_resource(script_path, "Script")
            updated: List[tuple[str, List[str]]] = []
            for hdr, lns in sections:
                if hdr.startswith("[node "):
                    m_name = re.search(r'name="([^"]+)"', hdr)
                    m_parent = re.search(r'parent="([^"]+)"', hdr)
                    node_name = m_name.group(1) if m_name else ""
                    is_root = (target_node in (".", "root", "Root") and m_parent is None) or (target_node == node_name)
                    if is_root:
                        lns = [l for l in lns if not l.strip().startswith("script =")]
                        lns.insert(0, f'script = ExtResource("{sc_id}")')
                updated.append((hdr, lns))
            sections = updated

    # 3. Handle add_nodes
    if add_nodes:
        conn_idx = len(sections)
        for i, (hdr, _) in enumerate(sections):
            if hdr.startswith("[connection "):
                conn_idx = i
                break
        for nd in add_nodes:
            name = nd.get("name", "NewNode")
            parent = nd.get("parent", ".")
            node_type = nd.get("type", "Node")
            inst = nd.get("instance")
            sc = nd.get("script")
            props = nd.get("properties", {})

            lines: List[str] = []
            if inst:
                inst_id = get_or_create_ext_resource(inst, "PackedScene")
                header = f'[node name="{name}" parent="{parent}" instance=ExtResource("{inst_id}")]'
            else:
                header = f'[node name="{name}" type="{node_type}" parent="{parent}"]'

            if sc:
                sc_id = get_or_create_ext_resource(sc, "Script")
                lines.append(f'script = ExtResource("{sc_id}")')

            for k, v in props.items():
                lines.append(f"{k} = {v}")

            lines.append("")
            sections.insert(conn_idx, (header, lines))
            conn_idx += 1

    # Recalculate load_steps
    ext_count = sum(1 for hdr, _ in sections if hdr.startswith("[ext_resource ") or hdr.startswith("[sub_resource "))
    if sections and sections[0][0].startswith("[gd_scene"):
        hdr0 = sections[0][0]
        if ext_count > 0:
            hdr0 = re.sub(r"load_steps=\d+\s*", "", hdr0)
            hdr0 = hdr0.replace("[gd_scene ", f"[gd_scene load_steps={ext_count + 1} ")
        else:
            hdr0 = re.sub(r"load_steps=\d+\s*", "", hdr0)
        sections[0] = (hdr0, sections[0][1])

    output_lines: List[str] = []
    for hdr, lns in sections:
        if hdr:
            output_lines.append(hdr)
        for l in lns:
            output_lines.append(l)
    return "\n".join(output_lines).strip() + "\n"


def create_scene(
    project_path: str,
    file_path: str,
    root_node_name: str = "",
    root_node_type: str = "Node2D",
    content: str = "",
    script_path: Optional[str] = None,
    nodes: Optional[List[Dict[str, Any]]] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Creates a new Godot 4 scene (.tscn)."""
    proj_dir = Path(project_path).resolve()
    if not proj_dir.exists():
        return {"success": False, "error": f"Project directory '{project_path}' does not exist."}

    if not file_path:
        return {"success": False, "error": "Missing 'file_path' parameter."}

    clean_rel = file_path.strip().replace("res://", "")
    if not clean_rel.endswith(".tscn") and not clean_rel.endswith(".scn"):
        clean_rel += ".tscn"

    target_file = sanitize_project_path(str(proj_dir), clean_rel)

    if target_file.exists() and not overwrite:
        return {
            "success": False,
            "error": f"Scene file '{clean_rel}' already exists. Use overwrite=true or call edit_scene to modify.",
        }

    if not content:
        node_name = root_node_name or target_file.stem
        if not node_name:
            node_name = "Root"
        fmt_ver = detect_godot_format_version(str(proj_dir))
        content = build_scene_content(
            root_node_name=node_name,
            root_node_type=root_node_type or "Node2D",
            script_path=script_path,
            nodes=nodes,
            format_version=fmt_ver,
        )

    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(content, encoding="utf-8")

    return {
        "success": True,
        "action_executed": "create_scene",
        "file_path": str(target_file.relative_to(proj_dir)),
        "bytes_written": len(content.encode("utf-8")),
        "content": content,
    }


def edit_scene(
    project_path: str,
    file_path: str,
    content: str = "",
    add_nodes: Optional[List[Dict[str, Any]]] = None,
    remove_nodes: Optional[List[str]] = None,
    attach_script: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Edits an existing Godot 4 scene (.tscn)."""
    proj_dir = Path(project_path).resolve()
    if not proj_dir.exists():
        return {"success": False, "error": f"Project directory '{project_path}' does not exist."}

    if not file_path:
        return {"success": False, "error": "Missing 'file_path' parameter."}

    clean_rel = file_path.strip().replace("res://", "")
    target_file = sanitize_project_path(str(proj_dir), clean_rel)

    if not target_file.exists():
        return {
            "success": False,
            "error": f"Scene file '{clean_rel}' does not exist to edit. Call create_scene first.",
        }

    if content:
        final_content = content
    elif add_nodes or remove_nodes or attach_script:
        existing = target_file.read_text(encoding="utf-8")
        final_content = apply_scene_modifications(
            existing,
            add_nodes=add_nodes,
            remove_nodes=remove_nodes,
            attach_script=attach_script,
        )
    else:
        return {
            "success": False,
            "error": "No modifications specified. Provide 'content', 'add_nodes', 'remove_nodes', or 'attach_script'.",
        }

    target_file.write_text(final_content, encoding="utf-8")
    return {
        "success": True,
        "action_executed": "edit_scene",
        "file_path": str(target_file.relative_to(proj_dir)),
        "bytes_written": len(final_content.encode("utf-8")),
        "content": final_content,
    }


def delete_scene(project_path: str, file_path: str) -> Dict[str, Any]:
    """Safely deletes a Godot 4 scene (.tscn) and its sidecar metadata."""
    proj_dir = Path(project_path).resolve()
    if not proj_dir.exists():
        return {"success": False, "error": f"Project directory '{project_path}' does not exist."}

    if not file_path:
        return {"success": False, "error": "Missing 'file_path' parameter."}

    clean_rel = file_path.strip().replace("res://", "")
    target_file = sanitize_project_path(str(proj_dir), clean_rel)

    if target_file.suffix not in (".tscn", ".scn"):
        return {
            "success": False,
            "error": f"Refusing to delete non-scene file '{clean_rel}'. Only .tscn and .scn files can be deleted via delete_scene.",
        }

    if not target_file.exists():
        return {
            "success": False,
            "error": f"Scene file '{clean_rel}' does not exist in project.",
        }

    target_file.unlink()

    # Clean up Godot metadata sidecars if present
    for sidecar_ext in (".uid", ".remap", ".import"):
        sidecar = target_file.with_name(target_file.name + sidecar_ext)
        if sidecar.exists():
            sidecar.unlink()

    return {
        "success": True,
        "action_executed": "delete_scene",
        "file_path": str(target_file.relative_to(proj_dir)),
        "message": f"Scene '{clean_rel}' deleted successfully.",
    }


def read_scene(project_path: str, file_path: str) -> Dict[str, Any]:
    """Reads a Godot 4 scene (.tscn) from the project."""
    proj_dir = Path(project_path).resolve()
    if not proj_dir.exists():
        return {"success": False, "error": f"Project directory '{project_path}' does not exist."}

    if not file_path:
        return {"success": False, "error": "Missing 'file_path' parameter."}

    clean_rel = file_path.strip().replace("res://", "")
    target_file = sanitize_project_path(str(proj_dir), clean_rel)

    if not target_file.exists():
        return {"success": False, "error": f"Scene file '{clean_rel}' not found in project."}

    text = target_file.read_text(encoding="utf-8", errors="replace")
    return {
        "success": True,
        "action_executed": "read_scene",
        "file_path": str(target_file.relative_to(proj_dir)),
        "content": text,
        "line_count": len(text.splitlines()),
    }


def execute_action(project_path: str, action: Dict[str, Any]) -> Dict[str, Any]:
    """Executes a structured action on a Godot project directory."""
    action_type = action.get("action_type")
    params = action.get("parameters", {})
    resolved_path = project_path or DEFAULT_PROJECT_PATH
    if not resolved_path:
        return {"success": False, "error": "Missing 'project_path' parameter."}

    proj_dir = Path(resolved_path).resolve()
    if not proj_dir.exists():
        return {"success": False, "error": f"Project directory '{resolved_path}' does not exist."}

    if action_type in ("create_or_update_script", "create_or_update_scene", "create_or_update_file"):
        rel_file = params.get("file_path")
        content = params.get("content", "")
        if not rel_file:
            return {"success": False, "error": "Missing 'file_path' in parameters."}

        target_file = sanitize_project_path(str(proj_dir), rel_file)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        if rel_file == "project.godot" and content.strip().startswith("[config_version="):
            content = re.sub(r"^\[config_version=([0-9]+)\]\s*", r"config_version=\1\n\n", content.strip())
        target_file.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "action_executed": action_type,
            "file_written": str(target_file.relative_to(proj_dir)),
            "bytes_written": len(content.encode("utf-8")),
        }

    elif action_type == "create_scene":
        return create_scene(
            project_path=str(proj_dir),
            file_path=params.get("file_path", ""),
            root_node_name=params.get("root_node_name", ""),
            root_node_type=params.get("root_node_type", "Node2D"),
            content=params.get("content", ""),
            script_path=params.get("script_path"),
            nodes=params.get("nodes"),
            overwrite=params.get("overwrite", False),
        )

    elif action_type == "edit_scene":
        return edit_scene(
            project_path=str(proj_dir),
            file_path=params.get("file_path", ""),
            content=params.get("content", ""),
            add_nodes=params.get("add_nodes"),
            remove_nodes=params.get("remove_nodes"),
            attach_script=params.get("attach_script"),
        )

    elif action_type == "delete_scene":
        return delete_scene(
            project_path=str(proj_dir),
            file_path=params.get("file_path", ""),
        )

    elif action_type == "read_file":
        rel_file = params.get("file_path")
        if not rel_file:
            return {"success": False, "error": "Missing 'file_path' in parameters."}

        target_file = sanitize_project_path(str(proj_dir), rel_file)
        if not target_file.exists():
            return {"success": False, "error": f"File '{rel_file}' not found in project."}

        text = target_file.read_text(encoding="utf-8", errors="replace")
        return {
            "success": True,
            "action_executed": "read_file",
            "file_path": rel_file,
            "content": text,
            "line_count": len(text.splitlines()),
        }

    elif action_type == "list_project_files":
        files: List[str] = []
        for root, dirs, filenames in os.walk(proj_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in filenames:
                if not f.startswith("."):
                    rel = Path(root, f).relative_to(proj_dir)
                    files.append(str(rel))
        return {
            "success": True,
            "action_executed": "list_project_files",
            "total_files": len(files),
            "files": sorted(files),
        }

    elif action_type == "run_project":
        exe = (
            os.environ.get("GODOT_BIN")
            or shutil.which("godot4")
            or shutil.which("godot")
            or (str(Path.home() / ".local" / "bin" / "godot4") if (Path.home() / ".local" / "bin" / "godot4").exists() else None)
            or ("/home/piet/Documents/dev/Godot_v4.7.2-stable_linux.arm64" if Path("/home/piet/Documents/dev/Godot_v4.7.2-stable_linux.arm64").exists() else None)
        )
        if not exe:
            return {"success": False, "error": "Godot 4 binary ('godot4' or 'godot') not found in PATH or standard locations."}

        cmd = [exe, "--headless", "--path", str(proj_dir), "--quit"]
        extra = params.get("command", "")
        if extra:
            cmd.extend(extra.split())

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            return {
                "success": proc.returncode == 0,
                "action_executed": "run_project",
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Godot execution timed out after 15s."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif action_type == "chat_response":
        return {
            "success": True,
            "action_executed": "chat_response",
            "message": params.get("message", ""),
        }

    return {"success": False, "error": f"Unknown action_type '{action_type}'."}


WEB_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Godot AI Studio — Local Agent</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(19, 27, 46, 0.85);
      --card-border: rgba(255, 255, 255, 0.08);
      --primary: #38bdf8;
      --primary-hover: #0284c7;
      --accent: #818cf8;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --success: #34d399;
      --danger: #f87171;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      background-image: 
        radial-gradient(circle at 15% 20%, rgba(56, 189, 248, 0.12) 0%, transparent 40%),
        radial-gradient(circle at 85% 80%, rgba(129, 140, 248, 0.10) 0%, transparent 40%);
    }
    header {
      padding: 1.25rem 2rem;
      border-bottom: 1px solid var(--card-border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      backdrop-filter: blur(12px);
      background: rgba(11, 15, 25, 0.7);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      font-size: 1.25rem;
      font-weight: 700;
      background: linear-gradient(135deg, #38bdf8, #818cf8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .brand span { font-size: 1.5rem; -webkit-text-fill-color: initial; }
    .status-pill {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.875rem;
      background: rgba(52, 211, 153, 0.1);
      border: 1px solid rgba(52, 211, 153, 0.3);
      color: var(--success);
      padding: 0.35rem 0.85rem;
      border-radius: 9999px;
    }
    .dot {
      width: 8px;
      height: 8px;
      background: var(--success);
      border-radius: 50%;
      box-shadow: 0 0 10px var(--success);
      animation: pulse 2s infinite;
    }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
    main {
      flex: 1;
      max-width: 960px;
      width: 100%;
      margin: 2rem auto;
      padding: 0 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1.75rem;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 1.75rem;
      backdrop-filter: blur(16px);
      box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.5);
    }
    .project-info {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--card-border);
      font-size: 0.875rem;
      color: var(--text-muted);
    }
    .project-info strong { color: var(--text); }
    label {
      display: block;
      font-weight: 600;
      margin-bottom: 0.6rem;
      font-size: 1rem;
    }
    textarea {
      width: 100%;
      min-height: 110px;
      background: rgba(11, 15, 25, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 12px;
      padding: 1rem;
      color: var(--text);
      font-family: inherit;
      font-size: 1rem;
      resize: vertical;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    textarea:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2);
    }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin: 1rem 0 1.5rem;
    }
    .chip {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: var(--text-muted);
      padding: 0.4rem 0.85rem;
      border-radius: 8px;
      font-size: 0.825rem;
      cursor: pointer;
      transition: all 0.2s;
      user-select: none;
    }
    .chip:hover {
      background: rgba(56, 189, 248, 0.15);
      border-color: rgba(56, 189, 248, 0.4);
      color: var(--text);
    }
    button {
      background: linear-gradient(135deg, #0284c7, #38bdf8);
      color: #0b0f19;
      border: none;
      padding: 0.9rem 1.75rem;
      font-size: 1rem;
      font-weight: 600;
      border-radius: 12px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      transition: transform 0.15s, box-shadow 0.15s;
    }
    button:hover:not(:disabled) {
      transform: translateY(-1px);
      box-shadow: 0 10px 20px -5px rgba(56, 189, 248, 0.4);
    }
    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .result-section {
      display: none;
      animation: fadeIn 0.3s ease-out;
    }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    .badge {
      display: inline-block;
      padding: 0.25rem 0.65rem;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .badge-success { background: rgba(52, 211, 153, 0.2); color: var(--success); }
    .thought-box {
      background: rgba(11, 15, 25, 0.5);
      border-left: 3px solid var(--accent);
      padding: 1rem;
      border-radius: 4px;
      margin: 1rem 0;
      font-size: 0.925rem;
      color: #cbd5e1;
    }
    pre {
      background: #05070c;
      border: 1px solid var(--card-border);
      padding: 1.25rem;
      border-radius: 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.875rem;
      overflow-x: auto;
      max-height: 400px;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span>🤖</span> Godot Local AI Studio
    </div>
    <div class="status-pill">
      <div class="dot"></div>
      <span id="gpuStatus">GPU Model Online</span>
    </div>
  </header>

  <main>
    <div class="card">
      <div class="project-info">
        <div style="display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap; width:100%;">
          <label style="margin:0; font-size:0.9rem;" for="projInput">Project:</label>
          <input type="text" id="projInput" style="flex:1; min-width:240px; background:rgba(11,15,25,0.7); border:1px solid rgba(255,255,255,0.15); border-radius:8px; padding:0.45rem 0.8rem; color:#f8fafc; font-family:monospace; font-size:0.85rem;" placeholder="/path/to/godot/project" />
          <button style="padding:0.45rem 0.9rem; font-size:0.825rem; border-radius:8px;" onclick="updateProject()">Switch Project</button>
        </div>
      </div>

      <label for="promptInput">Describe what you want to add or change in your game:</label>
      <textarea id="promptInput" placeholder="e.g. Add a coin magnet power-up that pulls coins toward the player..."></textarea>

      <div class="chips">
        <div class="chip" onclick="setPrompt(this.innerText)">🛡️ Add a shield power-up to runner game</div>
        <div class="chip" onclick="setPrompt(this.innerText)">🧲 Add a coin magnet that attracts coins within 200px</div>
        <div class="chip" onclick="setPrompt(this.innerText)">💨 Add a dash skill on Shift key</div>
        <div class="chip" onclick="setPrompt(this.innerText)">⭐ Add floating popup numbers when collecting coins</div>
      </div>

      <button id="submitBtn" onclick="generateAndApply()">
        <span>⚡</span> Generate & Apply to Godot
      </button>
    </div>

    <div id="resultCard" class="card result-section">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
        <h3 id="resultTitle">Applied Changes</h3>
        <span id="actionBadge" class="badge badge-success">APPLIED</span>
      </div>
      <div id="thoughtBox" class="thought-box"></div>
      <pre><code id="codeBlock"></code></pre>
    </div>
  </main>

  <script>
    async function loadStatus() {
      try {
        const res = await fetch('/health');
        const data = await res.json();
        const input = document.getElementById('projInput');
        if (input && (!input.value || input.value === 'Connecting...')) {
          input.value = data.default_project_path || '';
        }
        if (data.gpu) {
          document.getElementById('gpuStatus').innerText = data.gpu + ' Online';
        }
      } catch (e) {
        document.getElementById('projInput').value = 'Server offline';
      }
    }
    loadStatus();

    async function updateProject() {
      const p = document.getElementById('projInput').value.trim();
      if (!p) return;
      try {
        const res = await fetch('/v1/project', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_path: p })
        });
        const data = await res.json();
        if (data.success) {
          alert('✓ Switched default project to: ' + data.default_project_path);
        } else {
          alert('Error: ' + (data.error || 'Failed to switch project'));
        }
      } catch (e) {
        alert('Server connection error: ' + e.message);
      }
    }

    function setPrompt(text) {
      document.getElementById('promptInput').value = text;
      document.getElementById('promptInput').focus();
    }

    async function generateAndApply() {
      const prompt = document.getElementById('promptInput').value.trim();
      if (!prompt) return;

      const projPath = document.getElementById('projInput').value.trim();
      const btn = document.getElementById('submitBtn');
      const resultCard = document.getElementById('resultCard');
      const resultTitle = document.getElementById('resultTitle');
      const thoughtBox = document.getElementById('thoughtBox');
      const codeBlock = document.getElementById('codeBlock');

      btn.disabled = true;
      btn.innerHTML = '<span>⏳</span> AI is generating & applying...';

      try {
        const res = await fetch('/v1/act', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt, project_path: projPath })
        });
        const data = await res.json();

        resultCard.style.display = 'block';
        if (data.action) {
          thoughtBox.innerText = data.action.thought || 'Executed successfully.';
          const exec = data.execution || {};
          const fileWritten = exec.file_written || (data.action.parameters && data.action.parameters.file_path) || '';
          resultTitle.innerText = '✓ Applied: ' + fileWritten;
          const content = (data.action.parameters && data.action.parameters.content) || JSON.stringify(data.action, null, 2);
          codeBlock.innerText = content;
        } else {
          thoughtBox.innerText = JSON.stringify(data);
        }
      } catch (err) {
        resultCard.style.display = 'block';
        thoughtBox.innerText = 'Error: ' + err.message;
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>⚡</span> Generate & Apply to Godot';
      }
    }
  </script>
</body>
</html>
"""


class GodotAgentHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler supporting CORS and JSON endpoints."""

    def _send_json(self, status: HTTPStatus, data: Any) -> None:
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, status: HTTPStatus, html_content: str) -> None:
        payload = html_content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path in ("/", "/studio"):
            accept_header = self.headers.get("Accept", "")
            if "application/json" in accept_header and "text/html" not in accept_header:
                import torch
                gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "None"
                self._send_json(HTTPStatus.OK, {
                    "status": "online",
                    "service": "Godot Local AI Agent Server",
                    "model": BASE_MODEL,
                    "adapter": ADAPTER_PATH,
                    "device": DEVICE,
                    "gpu": gpu_name,
                    "cuda_available": torch.cuda.is_available(),
                    "default_project_path": DEFAULT_PROJECT_PATH,
                })
            else:
                self._send_html(HTTPStatus.OK, WEB_UI_HTML)

        elif path == "/health":
            import torch
            gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "None"
            self._send_json(HTTPStatus.OK, {
                "status": "online",
                "service": "Godot Local AI Agent Server",
                "model": BASE_MODEL,
                "adapter": ADAPTER_PATH,
                "device": DEVICE,
                "gpu": gpu_name,
                "cuda_available": torch.cuda.is_available(),
                "default_project_path": DEFAULT_PROJECT_PATH,
            })

        elif path == "/schema":
            if SCHEMA_PATH.exists():
                schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
                self._send_json(HTTPStatus.OK, schema)
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Schema file not found."})

        elif path == "/v1/scene":
            query = urllib.parse.parse_qs(parsed_url.query)
            file_path = query.get("file_path", [""])[0]
            proj_path = query.get("project_path", [""])[0] or DEFAULT_PROJECT_PATH
            if not proj_path or not file_path:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'file_path' or 'project_path' parameter."})
                return
            result = read_scene(proj_path, file_path)
            status = HTTPStatus.OK if result.get("success") else HTTPStatus.NOT_FOUND
            self._send_json(status, result)

        elif path == "/v1/plan/status":
            query = urllib.parse.parse_qs(parsed_url.query)
            proj_path = query.get("project_path", [""])[0] or DEFAULT_PROJECT_PATH
            if not proj_path:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'project_path' parameter."})
                return
            from logic.orchestrator.orchestrator import AutonomousProjectOrchestrator
            orch = AutonomousProjectOrchestrator(Path(proj_path))
            plan = orch.get_current_plan()
            if not plan:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "No active plan found on disk."})
            else:
                self._send_json(HTTPStatus.OK, plan.to_dict())

        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Endpoint '{path}' not found."})

    def do_POST(self) -> None:
        global DEFAULT_PROJECT_PATH
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"

        try:
            req_data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body."})
            return

        # 1. /v1/chat endpoint
        if path == "/v1/chat":
            prompt = req_data.get("prompt", "")
            session_id = req_data.get("session_id")
            messages = req_data.get("messages")

            if messages is None:
                if session_id:
                    with SESSIONS_LOCK:
                        if session_id not in SESSIONS:
                            SESSIONS[session_id] = [
                                {"role": "system", "content": "You are an expert Godot 4 Engine developer and autonomous AI agent."}
                            ]
                        if prompt:
                            SESSIONS[session_id].append({"role": "user", "content": prompt})
                        messages = list(SESSIONS[session_id])
                elif prompt:
                    messages = [
                        {"role": "system", "content": "You are an expert Godot 4 Engine developer and autonomous AI agent."},
                        {"role": "user", "content": prompt},
                    ]

            if not messages:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'prompt' or 'messages'."})
                return

            response_text = generate_text(
                messages,
                max_new_tokens=req_data.get("max_tokens", 1000),
                temperature=req_data.get("temperature", 0.5),
            )

            if session_id:
                with SESSIONS_LOCK:
                    SESSIONS[session_id].append({"role": "assistant", "content": response_text})

            self._send_json(HTTPStatus.OK, {
                "response": response_text,
                "session_id": session_id,
                "message_count": len(messages) + (1 if session_id else 0),
            })

        # 2. /v1/action endpoint: Returns structured action
        elif path == "/v1/action":
            prompt = req_data.get("prompt", "")
            if not prompt:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'prompt' field."})
                return

            session_id = req_data.get("session_id")
            project_context = req_data.get("project_context", "")
            user_msg = f"{prompt}\n\nProject context:\n{project_context}" if project_context else prompt

            if session_id:
                with SESSIONS_LOCK:
                    if session_id not in SESSIONS:
                        SESSIONS[session_id] = [
                            {"role": "system", "content": SYSTEM_ACTION_PROMPT}
                        ]
                    SESSIONS[session_id].append({"role": "user", "content": user_msg})
                    messages = list(SESSIONS[session_id])
            else:
                messages = [
                    {"role": "system", "content": SYSTEM_ACTION_PROMPT},
                    {"role": "user", "content": user_msg},
                ]

            raw_text = generate_text(
                messages,
                max_new_tokens=req_data.get("max_tokens", 1200),
                temperature=req_data.get("temperature", 0.3),
            )
            action = extract_json_from_text(raw_text)

            if session_id:
                with SESSIONS_LOCK:
                    SESSIONS[session_id].append({"role": "assistant", "content": raw_text})

            self._send_json(HTTPStatus.OK, {
                "action": action,
                "raw_generation": raw_text,
                "session_id": session_id,
            })

        # 2.5 /v1/project endpoint: Dynamically updates default project path
        elif path == "/v1/project":
            new_path = req_data.get("project_path")
            if not new_path:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'project_path' parameter."})
                return
            p = Path(new_path).resolve()
            if not p.exists() or not p.is_dir():
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"Project directory '{new_path}' does not exist."})
                return
            DEFAULT_PROJECT_PATH = str(p)
            self._send_json(HTTPStatus.OK, {
                "success": True,
                "default_project_path": DEFAULT_PROJECT_PATH,
                "message": f"Default Godot project path updated to: {DEFAULT_PROJECT_PATH}"
            })

        # 3. /v1/execute endpoint: Executes an action on a local Godot project
        elif path == "/v1/execute":
            project_path = req_data.get("project_path") or DEFAULT_PROJECT_PATH
            action = req_data.get("action")
            if not project_path or not action:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'project_path' or 'action'."})
                return

            exec_result = execute_action(project_path, action)
            self._send_json(HTTPStatus.OK, exec_result)

        # 4. /v1/act endpoint: Combined (generate action + execute on project)
        elif path == "/v1/act":
            prompt = req_data.get("prompt", "")
            project_path = req_data.get("project_path") or DEFAULT_PROJECT_PATH
            if not prompt or not project_path:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'prompt' or 'project_path'."})
                return

            # Read project tree for context
            list_res = execute_action(project_path, {"action_type": "list_project_files"})
            proj_files = list_res.get("files", []) if list_res.get("success") else []
            context_str = f"Available files: {', '.join(proj_files[:50])}"

            messages = [
                {"role": "system", "content": SYSTEM_ACTION_PROMPT},
                {"role": "user", "content": f"{prompt}\n\nProject Context:\n{context_str}"},
            ]

            raw_text = generate_text(messages, max_new_tokens=1200, temperature=0.3)
            action = extract_json_from_text(raw_text)
            exec_result = execute_action(project_path, action)

            self._send_json(HTTPStatus.OK, {
                "prompt": prompt,
                "action": action,
                "execution": exec_result,
            })

        # 5. /v1/scene/create endpoint: Creates a Godot 4 scene (.tscn)
        elif path == "/v1/scene/create":
            proj_path = req_data.get("project_path") or DEFAULT_PROJECT_PATH
            file_path = req_data.get("file_path", "")
            if not proj_path or not file_path:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'project_path' or 'file_path'."})
                return

            result = create_scene(
                project_path=proj_path,
                file_path=file_path,
                root_node_name=req_data.get("root_node_name", ""),
                root_node_type=req_data.get("root_node_type", "Node2D"),
                content=req_data.get("content", ""),
                script_path=req_data.get("script_path"),
                nodes=req_data.get("nodes"),
                overwrite=req_data.get("overwrite", False),
            )
            status = HTTPStatus.OK if result.get("success") else HTTPStatus.BAD_REQUEST
            self._send_json(status, result)

        # 6. /v1/scene/edit endpoint: Edits an existing Godot 4 scene (.tscn)
        elif path == "/v1/scene/edit":
            proj_path = req_data.get("project_path") or DEFAULT_PROJECT_PATH
            file_path = req_data.get("file_path", "")
            if not proj_path or not file_path:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'project_path' or 'file_path'."})
                return

            result = edit_scene(
                project_path=proj_path,
                file_path=file_path,
                content=req_data.get("content", ""),
                add_nodes=req_data.get("add_nodes"),
                remove_nodes=req_data.get("remove_nodes"),
                attach_script=req_data.get("attach_script"),
            )
            status = HTTPStatus.OK if result.get("success") else HTTPStatus.BAD_REQUEST
            self._send_json(status, result)

        # 7. /v1/scene/delete endpoint: Deletes a Godot 4 scene (.tscn)
        elif path == "/v1/scene/delete":
            proj_path = req_data.get("project_path") or DEFAULT_PROJECT_PATH
            file_path = req_data.get("file_path", "")
            if not proj_path or not file_path:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'project_path' or 'file_path'."})
                return

            result = delete_scene(project_path=proj_path, file_path=file_path)
            status = HTTPStatus.OK if result.get("success") else HTTPStatus.BAD_REQUEST
            self._send_json(status, result)

        # 8. /v1/plan: Generate dependency-aware project plan
        elif path == "/v1/plan":
            proj_path = req_data.get("project_path") or DEFAULT_PROJECT_PATH
            request_text = req_data.get("prompt") or req_data.get("user_request", "")
            if not proj_path or not request_text:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'project_path' or 'prompt'/'user_request'."})
                return
            from logic.orchestrator.orchestrator import AutonomousProjectOrchestrator
            orch = AutonomousProjectOrchestrator(Path(proj_path), generator_fn=generate_text)
            plan = orch.plan(request_text)
            self._send_json(HTTPStatus.OK, plan.to_dict())

        # 9. /v1/orchestrate: Full autonomous execution cycle
        elif path == "/v1/orchestrate":
            proj_path = req_data.get("project_path") or DEFAULT_PROJECT_PATH
            request_text = req_data.get("prompt") or req_data.get("user_request", "")
            max_repairs = req_data.get("max_repairs", 2)
            if not proj_path:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'project_path'."})
                return
            from logic.orchestrator.orchestrator import AutonomousProjectOrchestrator
            orch = AutonomousProjectOrchestrator(Path(proj_path), generator_fn=generate_text)
            if request_text:
                plan = orch.plan(request_text)
            else:
                plan = orch.get_current_plan()
                if not plan:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "No existing plan found and no prompt provided."})
                    return
            summary = orch.execute_plan(plan, max_repairs_per_task=max_repairs)
            self._send_json(HTTPStatus.OK, summary)

        # 10. /v1/plan/resume: Resume interrupted plan
        elif path == "/v1/plan/resume":
            proj_path = req_data.get("project_path") or DEFAULT_PROJECT_PATH
            max_repairs = req_data.get("max_repairs", 2)
            if not proj_path:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'project_path'."})
                return
            from logic.orchestrator.orchestrator import AutonomousProjectOrchestrator
            orch = AutonomousProjectOrchestrator(Path(proj_path), generator_fn=generate_text)
            try:
                summary = orch.resume_execution(max_repairs_per_task=max_repairs)
                self._send_json(HTTPStatus.OK, summary)
            except Exception as e:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})

        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Endpoint '{path}' not found."})

    def do_DELETE(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/v1/scene":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length).decode("utf-8")
                try:
                    req_data = json.loads(body)
                except json.JSONDecodeError:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body."})
                    return
            else:
                query = urllib.parse.parse_qs(parsed_url.query)
                req_data = {
                    "project_path": query.get("project_path", [""])[0],
                    "file_path": query.get("file_path", [""])[0],
                }

            proj_path = req_data.get("project_path") or DEFAULT_PROJECT_PATH
            file_path = req_data.get("file_path", "")
            if not proj_path or not file_path:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'project_path' or 'file_path'."})
                return

            result = delete_scene(project_path=proj_path, file_path=file_path)
            status = HTTPStatus.OK if result.get("success") else HTTPStatus.BAD_REQUEST
            self._send_json(status, result)
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Endpoint '{path}' not found for DELETE."})


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    no_model: bool = False,
    project_path: Optional[str] = None,
) -> None:
    """Launches the threaded Godot Agent HTTP server."""
    global DEFAULT_PROJECT_PATH
    if project_path:
        DEFAULT_PROJECT_PATH = str(Path(project_path).resolve())

    # Bind the socket first to fail fast if the port is already taken or locked
    server_address = (host, port)
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer(server_address, GodotAgentHTTPHandler)

    if not no_model:
        load_model_and_tokenizer()
    else:
        print("[INFO] Starting server in MOCK mode (no GPU model loaded).")
    print("=" * 60)
    print(f"  Godot Local AI Agent Server running at http://{host}:{port}")
    if DEFAULT_PROJECT_PATH:
        print(f"  Default Project Path: {DEFAULT_PROJECT_PATH}")
    print("  Endpoints:")
    print(f"    - Health:       GET  http://localhost:{port}/health")
    print(f"    - Action Schema GET  http://localhost:{port}/schema")
    print(f"    - Scene Read:   GET  http://localhost:{port}/v1/scene?file_path=...&project_path=...")
    print(f"    - Scene Create: POST http://localhost:{port}/v1/scene/create")
    print(f"    - Scene Edit:   POST http://localhost:{port}/v1/scene/edit")
    print(f"    - Scene Delete: POST http://localhost:{port}/v1/scene/delete (or DELETE /v1/scene)")
    print(f"    - Chat:         POST http://localhost:{port}/v1/chat")
    print(f"    - Action Gen:   POST http://localhost:{port}/v1/action")
    print(f"    - Exec Action:  POST http://localhost:{port}/v1/execute")
    print(f"    - End-to-End:   POST http://localhost:{port}/v1/act")
    print("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Godot Agent Server...")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Godot Local AI Agent HTTP Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--project-path", default=os.environ.get("GODOT_PROJECT_PATH"), help="Default Godot project path on disk")
    parser.add_argument("--no-model", action="store_true", help="Run without loading PyTorch weights (for testing endpoints)")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, no_model=args.no_model, project_path=args.project_path)
