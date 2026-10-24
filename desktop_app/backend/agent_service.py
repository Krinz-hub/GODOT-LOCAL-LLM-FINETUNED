"""Godot Autonomous AI Agent Service (FastAPI).

Provides full lifecycle management for the fine-tuned Qwen2.5-Coder model,
Godot 4 project detection, secure file editing with diffs & rollback,
Godot headless validation, and streaming token responses via Server-Sent Events (SSE).
"""

from __future__ import annotations

import asyncio
import difflib
import gc
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import threading
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GodotAgentService")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
DEFAULT_ADAPTER_PATH = str(REPO_ROOT / "godot-agent-lora" / "final_adapter")
SCHEMA_PATH = REPO_ROOT / "logic" / "schemas" / "godot_action.schema.json"

AUTH_TOKEN_FILE = Path.home() / ".godot_ai_agent" / "auth_token.txt"
AUTH_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
if not AUTH_TOKEN_FILE.exists():
    AUTH_TOKEN_FILE.write_text(secrets.token_hex(24), encoding="utf-8")
AUTH_TOKEN = AUTH_TOKEN_FILE.read_text(encoding="utf-8").strip()

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

# Global State
class ModelManager:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.model: Any = None
        self.tokenizer: Any = None
        self.pad_token_id: Optional[int] = None
        self.eos_token_ids: List[int] = []
        self.device: str = "cpu"
        self.state: str = "unloaded"  # unloaded | loading | ready | error
        self.base_model_path: str = DEFAULT_BASE_MODEL
        self.adapter_path: str = DEFAULT_ADAPTER_PATH
        self.error_message: Optional[str] = None
        self.loaded_at: Optional[float] = None
        self.active_generation_cancel_event = threading.Event()

    def get_info(self) -> Dict[str, Any]:
        gpu_info = "None"
        try:
            import torch
            if torch.cuda.is_available():
                gpu_info = f"{torch.cuda.get_device_name(0)} (VRAM: {torch.cuda.memory_allocated(0)/(1024**2):.1f}MB allocated)"
        except Exception:
            pass

        return {
            "state": self.state,
            "base_model": self.base_model_path,
            "adapter": self.adapter_path,
            "device": self.device,
            "gpu_info": gpu_info,
            "error_message": self.error_message,
            "loaded_at": self.loaded_at,
        }

    def unload(self) -> Dict[str, Any]:
        with self.lock:
            self.state = "unloaded"
            self.model = None
            self.tokenizer = None
            self.error_message = None
            self.loaded_at = None
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            logger.info("Model unloaded from memory.")
            return {"success": True, "message": "Model unloaded."}

    def load(
        self,
        base_model_path: Optional[str] = None,
        adapter_path: Optional[str] = None,
        device_map: str = "auto",
        load_in_4bit: bool = True,
    ) -> Dict[str, Any]:
        with self.lock:
            if self.state == "loading":
                return {"success": False, "error": "Model is currently loading."}
            if self.state == "ready":
                return {"success": True, "message": "Model is already loaded."}

            self.state = "loading"
            self.error_message = None

            base_path = base_model_path or self.base_model_path
            ad_path = adapter_path or self.adapter_path

            try:
                import torch
                from transformers import (
                    AutoModelForCausalLM,
                    AutoTokenizer,
                    BitsAndBytesConfig,
                    PreTrainedTokenizerBase,
                )
                from peft import PeftModel

                logger.info("Loading tokenizer from %s...", ad_path)
                tokenizer = AutoTokenizer.from_pretrained(ad_path)
                if not isinstance(tokenizer, PreTrainedTokenizerBase):
                    raise RuntimeError("Failed to load valid tokenizer.")

                logger.info("Loading base model: %s (4bit=%s)...", base_path, load_in_4bit)
                if load_in_4bit and torch.cuda.is_available():
                    quant_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.bfloat16,
                        bnb_4bit_use_double_quant=True,
                    )
                    base_model = AutoModelForCausalLM.from_pretrained(
                        base_path,
                        quantization_config=quant_config,
                        dtype=torch.bfloat16,
                        device_map=device_map,
                    )
                else:
                    base_model = AutoModelForCausalLM.from_pretrained(
                        base_path,
                        dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                        device_map=device_map if torch.cuda.is_available() else None,
                    )

                logger.info("Attaching LoRA adapter from %s...", ad_path)
                model = PeftModel.from_pretrained(base_model, ad_path)
                model.eval()

                # Tokens
                im_end_id = tokenizer.convert_tokens_to_ids("<|im_end|>")
                endoftext_id = tokenizer.convert_tokens_to_ids("<|endoftext|>")
                eos_ids: List[int] = []
                if isinstance(im_end_id, int) and im_end_id >= 0:
                    eos_ids.append(im_end_id)
                if isinstance(endoftext_id, int) and endoftext_id >= 0 and endoftext_id != im_end_id:
                    eos_ids.append(endoftext_id)
                if not eos_ids and tokenizer.eos_token_id is not None:
                    eos_ids = [tokenizer.eos_token_id]
                if not eos_ids:
                    eos_ids = [151645]

                pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else eos_ids[0]

                self.model = model
                self.tokenizer = tokenizer
                self.eos_token_ids = eos_ids
                self.pad_token_id = pad_id
                self.device = str(model.get_input_embeddings().weight.device)
                self.state = "ready"
                self.base_model_path = base_path
                self.adapter_path = ad_path
                self.loaded_at = time.time()
                logger.info("Model loaded successfully on %s", self.device)
                return {"success": True, "message": "Model loaded successfully", "device": self.device}

            except Exception as e:
                self.state = "error"
                self.error_message = str(e)
                logger.error("Failed to load model: %s", e)
                return {"success": False, "error": str(e)}


class ProjectManager:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.active_path: Optional[Path] = None
        self.project_name: Optional[str] = None
        self.godot_version: Optional[str] = None
        self.godot_executable: Optional[str] = None
        self.connection_method: Optional[str] = None  # "editor_plugin" | "manual_folder"
        self.last_seen: float = 0.0
        self.file_history: List[Dict[str, Any]] = []

    def set_project(
        self,
        path: str | Path,
        name: Optional[str] = None,
        godot_ver: Optional[str] = None,
        godot_bin: Optional[str] = None,
        method: str = "manual_folder",
    ) -> Dict[str, Any]:
        with self.lock:
            p = Path(path).resolve()
            if not p.exists() or not p.is_dir():
                raise ValueError(f"Project directory does not exist: {p}")

            project_godot = p / "project.godot"
            if not project_godot.exists():
                raise ValueError(f"No 'project.godot' found in {p}")

            # Parse project name if not given
            if not name:
                name = p.name
                try:
                    for line in project_godot.read_text(encoding="utf-8", errors="ignore").splitlines():
                        if line.strip().startswith("config/name="):
                            name = line.split("=", 1)[1].strip().strip('"')
                            break
                except Exception:
                    pass

            # Detect Godot version if not given
            if not godot_ver:
                fmt = 3
                try:
                    for line in project_godot.read_text(encoding="utf-8", errors="ignore").splitlines():
                        if line.strip().startswith("config_version="):
                            v = line.split("=", 1)[1].strip()
                            fmt = 2 if v == "4" else 3
                            break
                except Exception:
                    pass
                godot_ver = "Godot 3.x" if fmt == 2 else "Godot 4.x"

            self.active_path = p
            self.project_name = name
            self.godot_version = godot_ver
            self.godot_executable = godot_bin or self.resolve_godot_bin()
            self.connection_method = method
            self.last_seen = time.time()

            logger.info("Connected to project '%s' at %s via %s", name, p, method)
            return self.get_info()

    def get_info(self) -> Dict[str, Any]:
        with self.lock:
            if not self.active_path:
                return {
                    "connected": False,
                    "project_path": None,
                    "project_name": None,
                    "godot_version": None,
                    "godot_executable": self.resolve_godot_bin(),
                    "connection_method": None,
                }
            return {
                "connected": True,
                "project_path": str(self.active_path),
                "project_name": self.project_name,
                "godot_version": self.godot_version,
                "godot_executable": self.godot_executable,
                "connection_method": self.connection_method,
                "last_seen": self.last_seen,
            }

    @staticmethod
    def resolve_godot_bin() -> Optional[str]:
        candidates = [
            os.environ.get("GODOT_BIN"),
            "/home/piet/.local/bin/godot4",
            shutil.which("godot4"),
            shutil.which("godot"),
            "/usr/bin/godot3",
        ]
        for c in candidates:
            if c and Path(c).exists() and os.access(c, os.X_OK):
                return c
        return None

    def sanitize_path(self, relative_path: str) -> Path:
        if not self.active_path:
            raise ValueError("No Godot project connected.")
        base = self.active_path.resolve()
        target = (base / relative_path).resolve()
        if not str(target).startswith(str(base)):
            raise ValueError(f"Path traversal detected: {relative_path} outside {base}")
        # Protect against symlink escapes
        if target.is_symlink():
            real_target = target.resolve()
            if not str(real_target).startswith(str(base)):
                raise ValueError("Symlink traversal detected.")
        return target


model_mgr = ModelManager()
project_mgr = ProjectManager()

app = FastAPI(
    title="Godot Autonomous AI Agent Service",
    description="Local backend service for Godot autonomous AI agent desktop IDE",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication dependency for editor plugin registration
def verify_token(
    x_agent_token: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
) -> bool:
    received = x_agent_token or token
    if not received or received != AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing local authentication token.",
        )
    return True


# Models
class ProjectRegisterRequest(BaseModel):
    project_path: str
    project_name: Optional[str] = None
    godot_version: Optional[str] = None
    godot_executable: Optional[str] = None

class ProjectSelectRequest(BaseModel):
    project_path: str

class FileEditRequest(BaseModel):
    file_path: str
    content: str
    expected_hash: Optional[str] = None
    force: bool = False

class RollbackRequest(BaseModel):
    change_id: Optional[str] = None

class ChatPromptRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None
    max_tokens: int = 1200
    temperature: float = 0.4
    context: Optional[str] = None

class AgentActRequest(BaseModel):
    prompt: str
    auto_apply: bool = False
    session_id: Optional[str] = None

class GodotRunRequest(BaseModel):
    headless: bool = True
    scene: Optional[str] = None
    timeout: int = 20
    custom_args: Optional[str] = None


# Endpoints
@app.get("/health")
@app.get("/api/health")
def get_health() -> Dict[str, Any]:
    return {
        "status": "online",
        "service": "Godot AI Agent Desktop Service",
        "model": model_mgr.get_info(),
        "project": project_mgr.get_info(),
        "auth_token_configured": bool(AUTH_TOKEN),
    }

@app.get("/api/token")
def get_auth_token() -> Dict[str, str]:
    return {"token": AUTH_TOKEN}

@app.get("/api/model/status")
def get_model_status() -> Dict[str, Any]:
    return model_mgr.get_info()

@app.post("/api/model/load")
def load_model(payload: Dict[str, Any] = {}) -> Dict[str, Any]:
    return model_mgr.load(
        base_model_path=payload.get("base_model"),
        adapter_path=payload.get("adapter"),
        load_in_4bit=payload.get("load_in_4bit", True),
    )

@app.post("/api/model/unload")
def unload_model() -> Dict[str, Any]:
    return model_mgr.unload()

@app.post("/api/chat/cancel")
def cancel_generation() -> Dict[str, Any]:
    model_mgr.active_generation_cancel_event.set()
    return {"cancelled": True}

# Godot Project Endpoints
@app.post("/api/project/register")
def register_project(req: ProjectRegisterRequest, _auth: bool = Depends(verify_token)) -> Dict[str, Any]:
    try:
        info = project_mgr.set_project(
            path=req.project_path,
            name=req.project_name,
            godot_ver=req.godot_version,
            godot_bin=req.godot_executable,
            method="editor_plugin",
        )
        return {"success": True, "project": info}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/project/select")
def select_project(req: ProjectSelectRequest) -> Dict[str, Any]:
    try:
        info = project_mgr.set_project(path=req.project_path, method="manual_folder")
        return {"success": True, "project": info}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/project/status")
def get_project_status() -> Dict[str, Any]:
    return project_mgr.get_info()

@app.get("/api/project/files")
def list_project_files() -> Dict[str, Any]:
    info = project_mgr.get_info()
    if not info.get("connected") or not project_mgr.active_path:
        raise HTTPException(status_code=400, detail="No project connected.")

    root = project_mgr.active_path
    ignored_dirs = {".git", ".godot", ".import", ".agent_backup", "__pycache__"}
    files_list: List[Dict[str, Any]] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignored_dirs and not d.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            full_path = Path(dirpath, fn)
            rel_path = str(full_path.relative_to(root))
            ext = full_path.suffix.lower()
            kind = "other"
            if ext == ".gd":
                kind = "script"
            elif ext == ".tscn":
                kind = "scene"
            elif ext in (".tres", ".res"):
                kind = "resource"
            elif fn == "project.godot":
                kind = "config"
            elif ext in (".png", ".svg", ".webp", ".jpg"):
                kind = "asset"

            files_list.append({
                "path": rel_path,
                "name": fn,
                "kind": kind,
                "size": full_path.stat().st_size,
                "mtime": full_path.stat().st_mtime,
            })

    files_list.sort(key=lambda x: (x["kind"] != "scene", x["kind"] != "script", x["path"]))
    return {"total": len(files_list), "files": files_list}

@app.get("/api/project/file")
def read_project_file(path: str = Query(...)) -> Dict[str, Any]:
    try:
        target = project_mgr.sanitize_path(path)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail=f"File '{path}' does not exist.")

        raw_bytes = target.read_bytes()
        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content = raw_bytes.decode("latin-1", errors="replace")

        sha = hashlib.sha256(raw_bytes).hexdigest()
        return {
            "path": path,
            "content": content,
            "hash": sha,
            "mtime": target.stat().st_mtime,
            "lines": len(content.splitlines()),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/project/edit")
def edit_project_file(req: FileEditRequest) -> Dict[str, Any]:
    try:
        target = project_mgr.sanitize_path(req.file_path)
        original_content = ""
        orig_hash = ""

        if target.exists():
            orig_bytes = target.read_bytes()
            orig_hash = hashlib.sha256(orig_bytes).hexdigest()
            if req.expected_hash and not req.force and orig_hash != req.expected_hash:
                raise HTTPException(
                    status_code=409,
                    detail="Conflict: File was modified externally since last read.",
                )
            original_content = orig_bytes.decode("utf-8", errors="replace")

        # Generate unified diff
        diff_lines = list(difflib.unified_diff(
            original_content.splitlines(keepends=True),
            req.content.splitlines(keepends=True),
            fromfile=f"a/{req.file_path}",
            tofile=f"b/{req.file_path}",
        ))
        diff_text = "".join(diff_lines)

        # Create backup
        backup_dir = project_mgr.active_path / ".agent_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        change_id = f"{int(time.time()*1000)}_{secrets.token_hex(4)}"
        backup_file = backup_dir / f"{change_id}_{Path(req.file_path).name}.bak"
        if target.exists():
            shutil.copy2(target, backup_file)

        # Write new content
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(req.content, encoding="utf-8")

        # Store in rollback history
        record = {
            "id": change_id,
            "file_path": req.file_path,
            "timestamp": time.time(),
            "diff": diff_text,
            "backup_file": str(backup_file) if target.exists() else None,
            "previous_content": original_content,
        }
        project_mgr.file_history.append(record)

        return {
            "success": True,
            "change_id": change_id,
            "file_path": req.file_path,
            "diff": diff_text,
            "bytes_written": len(req.content.encode("utf-8")),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/project/rollback")
def rollback_change(req: RollbackRequest) -> Dict[str, Any]:
    if not project_mgr.file_history:
        raise HTTPException(status_code=404, detail="No changes to rollback.")

    record = None
    if req.change_id:
        for r in reversed(project_mgr.file_history):
            if r["id"] == req.change_id:
                record = r
                break
    else:
        record = project_mgr.file_history[-1]

    if not record:
        raise HTTPException(status_code=404, detail="Change ID not found.")

    target = project_mgr.sanitize_path(record["file_path"])
    if record["backup_file"] and Path(record["backup_file"]).exists():
        shutil.copy2(record["backup_file"], target)
    else:
        target.write_text(record["previous_content"], encoding="utf-8")

    project_mgr.file_history.remove(record)
    return {"success": True, "reverted_change": record["id"], "file_path": record["file_path"]}

@app.get("/api/project/history")
def get_change_history() -> Dict[str, Any]:
    return {"history": list(reversed(project_mgr.file_history[-20:]))}

# Godot Headless Execution & Validation
@app.post("/api/godot/run")
def run_godot(req: GodotRunRequest) -> Dict[str, Any]:
    info = project_mgr.get_info()
    if not info.get("connected") or not project_mgr.active_path:
        raise HTTPException(status_code=400, detail="No project connected.")

    exe = project_mgr.godot_executable or project_mgr.resolve_godot_bin()
    if not exe:
        raise HTTPException(status_code=404, detail="Godot executable not found on system.")

    proj_dir = str(project_mgr.active_path)
    cmd = [exe, "--path", proj_dir]
    if req.headless:
        cmd.extend(["--headless", "--quit"])
    if req.scene:
        clean_scene = req.scene if req.scene.startswith("res://") else f"res://{req.scene.lstrip('/')}"
        cmd.append(clean_scene)
    if req.custom_args:
        # Strictly sanitize custom args: allow only safe Godot flags
        safe_args = [a for a in req.custom_args.split() if a.startswith("--") and not any(c in a for c in ";|&$`")]
        cmd.extend(safe_args)

    start_time = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=req.timeout)
        duration = time.time() - start_time
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_seconds": round(duration, 3),
            "command": " ".join(cmd),
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "exit_code": -1,
            "error": f"Execution timed out after {req.timeout}s",
            "stdout": "",
            "stderr": "TimeoutExpired",
            "command": " ".join(cmd),
        }

@app.post("/api/godot/validate")
def validate_project() -> Dict[str, Any]:
    """Runs Godot in headless check mode and parses for script/scene compilation errors."""
    res = run_godot(GodotRunRequest(headless=True, timeout=15))
    stdout = res.get("stdout", "")
    stderr = res.get("stderr", "")
    combined = f"{stdout}\n{stderr}"

    errors: List[str] = []
    warnings: List[str] = []

    for line in combined.splitlines():
        line_clean = line.strip()
        if "SCRIPT ERROR:" in line or "Parse Error:" in line or "ERROR:" in line:
            errors.append(line_clean)
        elif "WARNING:" in line or "SCRIPT WARNING:" in line:
            warnings.append(line_clean)

    is_valid = (res.get("success") is True) and (len(errors) == 0)
    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "raw_output": combined,
        "exit_code": res.get("exit_code"),
    }

# Agent & Streaming Inference
def parse_agent_response(text: str) -> Dict[str, Any]:
    # Import parser from godot_agent_server
    import sys
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from godot_agent_server import extract_json_from_text
    from godot_chat import extract_actions_or_code_blocks

    parsed = extract_json_from_text(text)
    if parsed.get("action_type") and parsed.get("action_type") != "chat_response":
        return parsed

    # Fallback to code blocks
    blocks = extract_actions_or_code_blocks(text)
    if blocks:
        return blocks[0]

    return {
        "thought": "Direct conversational response",
        "action_type": "chat_response",
        "parameters": {"message": text.strip()},
    }


@app.post("/api/chat/stream")
async def chat_stream(req: ChatPromptRequest) -> StreamingResponse:
    if model_mgr.state != "ready":
        # If model is not loaded, stream an informative error
        async def err_gen():
            msg = f"Model is not loaded (current status: {model_mgr.state}). Please load the model first via the Model Settings top bar."
            yield f"data: {json.dumps({'type': 'error', 'content': msg})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    model_mgr.active_generation_cancel_event.clear()

    # Build prompt messages
    info = project_mgr.get_info()
    ctx_prefix = ""
    if info.get("connected") and project_mgr.active_path:
        ctx_prefix = f"\nTarget project: {info.get('project_path')} ({info.get('godot_version', 'Godot 4')})"

    system_prompt = f"{SYSTEM_ACTION_PROMPT}{ctx_prefix}"
    user_prompt = req.prompt
    if req.context:
        user_prompt = f"{req.prompt}\n\nContext:\n{req.context}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    async def event_generator() -> AsyncGenerator[str, None]:
        from transformers import TextIteratorStreamer
        import torch

        tokenizer = model_mgr.tokenizer
        model = model_mgr.model

        raw_inputs = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        )
        input_device = getattr(model, "device", torch.device(model_mgr.device))
        inputs = {k: v.to(input_device) if isinstance(v, torch.Tensor) else v for k, v in raw_inputs.items()}

        streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
        gen_kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=req.max_tokens,
            temperature=req.temperature,
            do_sample=True,
            repetition_penalty=1.05,
            pad_token_id=model_mgr.pad_token_id,
            eos_token_id=model_mgr.eos_token_ids,
        )

        loop = asyncio.get_running_loop()
        gen_thread = threading.Thread(target=model.generate, kwargs=gen_kwargs)
        gen_thread.start()

        full_output = ""
        try:
            for new_text in streamer:
                if model_mgr.active_generation_cancel_event.is_set():
                    yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                    break
                full_output += new_text
                yield f"data: {json.dumps({'type': 'token', 'content': new_text})}\n\n"
                await asyncio.sleep(0.001)

            # Once complete, parse structured action
            action = parse_agent_response(full_output)
            yield f"data: {json.dumps({'type': 'action', 'action': action})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/agent/execute-action")
def execute_agent_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    action = payload.get("action")
    if not action:
        raise HTTPException(status_code=400, detail="Missing 'action'.")

    info = project_mgr.get_info()
    if not info.get("connected") or not project_mgr.active_path:
        raise HTTPException(status_code=400, detail="No Godot project connected.")

    import sys
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from godot_agent_server import execute_action

    res = execute_action(str(project_mgr.active_path), action)
    return res


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("AGENT_PORT", 8000))
    logger.info("Starting Godot Agent Service on port %d...", port)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
