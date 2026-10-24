# Godot Autonomous AI Agent Desktop IDE

A professional, minimal desktop IDE and pair programmer for Godot 4 engine, powered by our fine-tuned `Qwen2.5-Coder-7B-Instruct` model and `godot-agent-lora` adapter.

---

## 1. System Architecture

```
┌────────────────────────────────────────────────────────┐
│               Godot 4 Editor Project                   │
│         [addons/godot_ai_agent/plugin.gd]              │
│    - Auto-registers project directory over HTTP        │
│    - Authenticated via ~/.godot_ai_agent/auth_token    │
│    - Re-registers upon editor restart                  │
└───────────────────────────┬────────────────────────────┘
                            │ Localhost HTTP (Port 8000)
                            ▼
┌────────────────────────────────────────────────────────┐
│             Desktop Application (Electron)             │
│   ┌────────────────────────────────────────────────┐   │
│   │   React 18 + TypeScript + Vite + Tailwind CSS  │   │
│   │   - Left Sidebar: Project Explorer (gd, tscn)  │   │
│   │   - Center: Agent Chat, SSE Streaming, Diffs   │   │
│   │   - Right: Godot Logs, Validation, Rollback    │   │
│   │   - Top: Model Status & Engine Run Controls    │   │
│   └───────────────────────┬────────────────────────┘   │
│                           │ Secure IPC (Context Isolation)
│   ┌───────────────────────▼────────────────────────┐   │
│   │         Electron Main Process & Preload        │   │
│   │   - Native Godot Folder Picker                 │   │
│   │   - Process Lifecycle Management               │   │
│   └───────────────────────┬────────────────────────┘   │
└───────────────────────────┼────────────────────────────┘
                            │ REST & SSE Streaming
                            ▼
┌────────────────────────────────────────────────────────┐
│            Python Agent Service (FastAPI)              │
│   - Endpoints: /api/chat/stream, /api/model/*          │
│   - Godot AST Scene Builder & GDScript Modifier        │
│   - Safe Path Traversal & Symlink Escape Protection    │
│   - Backup & Atomic Reversible Rollback Engine         │
│   - Headless Godot Parse Error Validation              │
└───────────────────────────┬────────────────────────────┘
                            │ Inference (4-Bit NF4 bfloat16)
                            ▼
┌────────────────────────────────────────────────────────┐
│          Qwen2.5-Coder-7B-Instruct Base Model          │
│          + godot-agent-lora / final_adapter            │
└────────────────────────────────────────────────────────┘
```

---

## 2. Requirements & Prerequisites

- **Node.js**: `v20+` or `v22+` (System verified: `v22.14.0`, npm `10.9.2`)
- **Python**: `3.10+` or `3.12+` with virtual environment (`.venv`)
- **GPU (Optional for Local GPU Inference)**: NVIDIA GPU with CUDA support (e.g. GB10 / RTX / DGX)
- **Godot Engine**: Godot 4.x installed (e.g. `godot4` or `/home/piet/.local/bin/godot4`)

---

## 3. Installation

From the repository root:

```bash
# 1. Activate the Python virtual environment
source .venv/bin/activate

# 2. Navigate to the desktop application directory
cd desktop_app

# 3. Install frontend and Electron dependencies
npm install
```

---

## 4. Launching the Application

### Development Mode (with Live Hot-Reloading):
```bash
# Terminal 1: Start Vite dev server & compile Electron
npm run dev

# Terminal 2: Launch Electron
npm run start
```

### Production Build & Launch:
```bash
# Compile both the React Vite frontend and Electron main/preload
npm run build

# Launch the desktop application
npm run start
```

### Packaging into Desktop App Distribution:
```bash
# Package as a standalone Linux binary (AppImage / directory)
npm run package
```

---

## 5. Godot Project Connection

The IDE supports two real connection modes:

### Mode A: Automatic Godot 4 Editor Detection (Recommended)
1. Copy the plugin directory into your Godot project:
   ```bash
   cp -r desktop_app/godot_plugin/addons/godot_ai_agent /path/to/your/godot_project/addons/
   ```
2. Open your project in **Godot 4**.
3. Navigate to **Project -> Project Settings -> Plugins** and check **Enable** next to **Godot AI Agent Connector**.
4. The plugin automatically reads your local authentication token (`~/.godot_ai_agent/auth_token.txt`) and registers with the Desktop IDE over `http://127.0.0.1:8000/api/project/register`.
5. The Desktop IDE top bar immediately turns green: `Editor Plugin • <ProjectName>`.

### Mode B: Manual Folder Selection
1. Click **Select Godot Project** or the Folder icon in the IDE Top Bar.
2. Select your Godot project directory.
3. The IDE validates that `project.godot` exists and loads the project scripts, scenes, and configuration.

---

## 6. Model Loading & Inference Controls

1. Click on the **Model Status Pill** in the top bar to open the **Model Configuration Modal**.
2. **Base Model**: Defaults to `Qwen/Qwen2.5-Coder-7B-Instruct` (cached in HuggingFace cache).
3. **Adapter Path**: Defaults to `godot-agent-lora/final_adapter`.
4. Click **Load Model**.
   - The model loads in 4-bit NF4 (`BitsAndBytesConfig`) with `bfloat16` to minimize VRAM footprint.
   - When loaded, status changes to `Ready` with green indicator.
5. Generation can be stopped at any time using the **Stop** button in the Composer.
6. Click **Unload** to free GPU VRAM when done.

---

## 7. Safe Editing & Rollback Engine

- **Sandbox Boundary**: File edits and reads are strictly restricted to the connected Godot project root. Traversal (`../../`) and symlink escapes are rejected.
- **Diff Preview**: All code changes proposed by the AI agent require user approval (`Approve & Apply to Godot` vs `Dismiss`).
- **Conflict Detection**: Optimistic hashing prevents overwriting files modified externally in the Godot editor.
- **Rollback**: Every applied edit creates an automatic backup in `.agent_backup/`. The **Revert** action in the Activity Panel restores previous content seamlessly.

---

## 8. Godot Engine Execution & Validation

- **Validate**: Runs Godot headlessly (`godot4 --headless --quit`) to check syntax, scene definitions, and missing node dependencies without launching gameplay.
- **Run Project**: Launches the Godot project and streams stdout/stderr output into the **Output** panel.

---

## 9. Troubleshooting Guide

| Issue | Cause | Solution |
|---|---|---|
| **Port 8000 already in use** | An older `godot_agent_server.py` is running | Run `lsof -i :8000` and kill the old process, or export `AGENT_PORT=8080`. |
| **CUDA out of memory (OOM)** | Another process is consuming GPU VRAM | Unload other models or ensure `Load in 4-bit` is enabled in Model Configuration. |
| **Godot 4 binary not found** | `godot4` is not in standard PATH | Export `GODOT_BIN=/home/piet/.local/bin/godot4` or configure it in `.env`. |
| **Plugin 401 Unauthorized** | Token mismatch | Ensure `~/.godot_ai_agent/auth_token.txt` is readable by the Godot process. |
| **Electron Sandbox SUID Error** | Ubuntu non-root electron requirement | Launch with `npm run start` (which passes `--no-sandbox`). |
