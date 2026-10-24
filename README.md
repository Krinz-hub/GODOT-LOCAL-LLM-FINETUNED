# 🎮 Godot Local AI Agent & Autonomous Engineering Ecosystem

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Engine: Godot 4.x](https://img.shields.io/badge/Godot-4.x-478cbf?logo=godot-engine&logoColor=white)](https://godotengine.org)
[![Model: Qwen2.5-Coder-7B](https://img.shields.io/badge/Model-Qwen2.5--Coder--7B--Instruct-blueviolet)](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct)
[![Benchmark Score](https://img.shields.io/badge/Benchmark-90.0%25-brightgreen)](reports/model_eval_benchmark.json)
[![Privacy: 100% Local](https://img.shields.io/badge/Privacy-100%25_Local_Inference-success)](godot_agent_server.py)

An autonomous, local-first AI game development copilot and engineering ecosystem fine-tuned specifically for **Godot 4**. 

Unlike generic LLMs (which hallucinate deprecated Godot 3 syntax and understand only plaintext code), this system natively parses **`.tscn` scene trees, node hierarchies, signal connections, and typed GDScript 2.0**. It executes structured actions directly inside your Godot project with headless validation and atomic rollbacks—running **100% privately on local consumer or workstation hardware**.

---

## 🌟 Key Capabilities

* **Engine-Aware Autonomous Agent**: Generates and modifies `.tscn` scene graphs, instantiates nodes (`CharacterBody2D`, `CollisionShape2D`, `Area2D`), wires signals, and edits scripts via structured JSON actions.
* **Specialized Godot 4 Fine-Tuning**: Fine-tuned on `Qwen2.5-Coder-7B-Instruct` using 4-bit QLoRA over a curated corpus of 81,764 production records and 689 project graphs.
* **Tri-Tier Ecosystem**:
  1. **Core Agent Server (`godot_agent_server.py`)**: Local REST API and SSE streaming server with AST scene construction, security path sandboxing, and atomic snapshot rollbacks.
  2. **Desktop IDE (`desktop_app/`)**: Full-featured Electron + React 18 + TypeScript + Vite + Tailwind desktop interface with live project explorer, chat, streaming diffs, and engine controls.
  3. **In-Engine Bridge (`godot_bridge/` & `desktop_app/godot_plugin/`)**: Native Godot 4 GDScript editor plugin connecting the engine directly to the AI agent.
* **Headless Self-Healing**: Automatically runs Godot headless checks in the background to validate compilation and catch errors before applying changes.
* **100% Offline & Private**: Zero telemetry, zero cloud dependencies, and zero IP leaks.

---

## 📁 Repository File Structure

```text
GODOT-LOCAL-LLM-FINETUNED/
├── README.md                            # Comprehensive project guide and architectural documentation
├── .gitignore                           # Git ignore rules for datasets, builds, and model weights
├── dataset_index.json                   # Multi-stage dataset registry and stage mapping
├── etl_statistics.json                  # Historical ETL pipeline processing metrics
├── manifest.json                        # Dataset integrity manifest and SHA256 checksums
├── statistics.json                      # Ingestion and token distribution statistics
├── pyrefly.toml                         # Pyrefly static analysis configuration
├── pyrightconfig.json                   # Pyright Python type checker configuration
│
├── godot_agent_server.py                # Core Autonomous Agent Server (HTTP REST / SSE / AST / Engine Execution)
├── godot_chat.py                        # Interactive CLI terminal client for chatting with the agent
├── train_dgx.py                         # Distributed QLoRA 4-bit fine-tuning script for Grace-Blackwell / DGX
│
├── desktop_app/                         # Desktop IDE Application (Electron + React 18 + TypeScript + Vite)
│   ├── README.md                        # Desktop IDE installation, architecture, and developer manual
│   ├── package.json                     # Node.js project specification and dependency list
│   ├── vite.config.ts                   # Vite build configuration with Electron integration
│   ├── electron/                        # Electron main process and secure preload IPC bridge
│   │   ├── main.ts                      # Window lifecycle, native folder dialogs, and backend process manager
│   │   └── preload.ts                   # Context-isolated IPC API bridge
│   ├── src/                             # React frontend user interface
│   │   ├── App.tsx                      # Primary layout and view orchestrator
│   │   ├── components/                  # UI components (ChatArea, Composer, LeftSidebar, ActivityPanel, TopBar)
│   │   ├── services/api.ts              # REST and Server-Sent Events (SSE) API client
│   │   └── types/                       # TypeScript definitions for agent actions, diffs, and project files
│   ├── backend/                         # Desktop auxiliary backend service
│   │   └── agent_service.py             # FastAPI streaming service connecting UI to the agent core
│   └── godot_plugin/                    # In-editor Godot 4 plugin addon
│       └── addons/godot_ai_agent/       # Plugin configuration and background synchronization script
│
├── godot_bridge/                        # Standalone Godot 4 Editor Integration Bridge
│   ├── README.md                        # Bridge documentation and integration tutorial
│   └── godot_ai_bridge.gd               # Native Godot 4 GDScript HTTP client for autonomous editor actions
│
├── logic/                               # Modular ETL Data Engineering & Analysis Pipeline
│   ├── README.md                        # Data engineering architecture and pipeline documentation
│   ├── pyproject.toml                   # Pipeline package specification and CLI entry points
│   ├── requirements.txt                 # Python dependencies for extraction and analysis
│   ├── run_scraper.sh                   # Scraper execution helper
│   ├── config/                          # Pipeline YAML configurations
│   │   ├── pipeline.yaml                # Global paths, seeds, batch sizes, and train/val splits
│   │   ├── sources.yaml                 # Configured sources (local projects, GitHub, official Godot docs)
│   │   ├── cleaning_rules.yaml          # PII redaction, bloat purge, and Godot 4 upgrade rules
│   │   └── validation_rules.yaml        # Headless Godot validation flags and schema constraints
│   ├── schemas/                         # Formal JSON schemas ensuring deterministic agent outputs
│   │   ├── godot_action.schema.json     # Strict schema for autonomous agent JSON actions
│   │   ├── project.schema.json          # Project architecture and dependency schema
│   │   ├── production_logic.schema.json # 14-key game production planning schema
│   │   ├── agent_trajectory.schema.json # Step-by-step tool invocation trajectory schema
│   │   ├── debugging_repair.schema.json # Stack trace diagnosis and unified diff schema
│   │   ├── source_record.schema.json    # Ingested raw source artifact schema
│   │   └── dataset_metadata.schema.json # Dataset manifest and provenance schema
│   ├── src/logic_pipeline/              # Core pipeline implementation
│   │   ├── analysis/                    # NetworkX scene and project dependency graph analyzers
│   │   ├── extractors/                  # Static AST parsers (GDScript, scenes, resources, configs, diffs)
│   │   ├── processing/                  # Normalization, deduplication, quality filters, and export
│   │   ├── sources/                     # Source connectors for GitHub, local repos, and Godot docs
│   │   ├── validation/                  # Canonical schema and headless Godot validation checks
│   │   └── reporting/                   # Statistical and quality report generators
│   └── tests/                           # Unit and integration test suite
│       ├── test_agent_server.py         # Tests for agent server endpoints and action execution
│       ├── test_godot_adapter.py        # Tests for Godot LoRA adapter inference
│       ├── test_model_evaluation.py     # Tests for automated evaluation harnesses
│       └── test_schemas.py              # Tests for JSON schema validation
│
├── reports/                             # Evaluation Benchmarks, Empirical Studies & Quality Audits
│   ├── model_eval_benchmark.json        # Standardized benchmark output (90% score across game mechanics)
│   ├── best_prompting_strategies.md     # Production prompting guide and comparative findings
│   ├── prompt_experiments.md            # Systematic analysis of ReAct, CoT, and Action JSON schemas
│   ├── prompt_experiments.jsonl         # Raw trial logs for prompt benchmarking
│   ├── quality_report.md                # Dataset cleanliness and validation audit report
│   └── quality_report.json              # Programmatic quality statistics
│
├── scripts/                             # Utility & Evaluation Automation Scripts
│   ├── eval_benchmark.py                # Automated benchmark harness evaluating mechanics and API compliance
│   ├── clean_and_enrich_dataset.py      # Cleans, strips comments, and enriches training pairs
│   ├── generate_reports.py              # Builds Markdown and JSON performance reports
│   └── run_model_step.py                # Standalone diagnostic single-inference runner
│
├── godot_training_workspace/            # Fine-Tuning Workspace
│   ├── scripts/CLEANER.PY               # Specialized dataset formatting routines
│   └── data/                            # Partitioned training files (train.jsonl)
│
└── [Ignored Local Assets]               # Preserved locally; excluded from Git via .gitignore
    ├── godot-agent-lora/                # Fine-tuned Qwen2.5-Coder LoRA adapter weights
    ├── checkpoints/                     # Training checkpoints
    ├── raw/, cleaned/, deduplicated/    # Raw and intermediate crawler data
    ├── final/, structured/, quarantine/ # Partitioned dataset stages
    └── 2d_platformer/                   # Local Godot 4 testing and verification game project
```

---

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Godot 4 Engine / Editor                   │
│             [addons/godot_ai_agent/ or Bridge]               │
│   - Live project graph synchronization                       │
│   - In-engine action execution & scene reloading             │
└──────────────────────────────┬───────────────────────────────┘
                               │ Localhost HTTP / SSE
                               ▼
┌──────────────────────────────────────────────────────────────┐
│              Desktop IDE (Electron + React 18)               │
│   - Project Explorer (live .gd & .tscn tree)                 │
│   - Streaming Chat, Visual Diffs & Engine Controls           │
│   - Headless Diagnostics & One-Click Rollbacks               │
└──────────────────────────────┬───────────────────────────────┘
                               │ REST API
                               ▼
┌──────────────────────────────────────────────────────────────┐
│             Godot AI Agent Server (Port 8000)                │
│   - godot_agent_server.py                                    │
│   - Structured Action Schema Validator (JSON)                │
│   - Godot AST Scene Builder & GDScript Modifier              │
│   - Safe Path Sandboxing & Atomic File Rollback Engine       │
│   - Headless Godot Parse Error Validation                    │
└──────────────────────────────┬───────────────────────────────┘
                               │ 4-Bit NF4 bfloat16 Inference
                               ▼
┌──────────────────────────────────────────────────────────────┐
│            Qwen2.5-Coder-7B-Instruct Base Model              │
│            + godot-agent-lora Fine-Tuned Adapter             │
└──────────────────────────────────────────────────────────────┘
```

---

## ⚡ Structured Action Schema

The agent operates through strict, verifiable JSON actions conforming to [`logic/schemas/godot_action.schema.json`](logic/schemas/godot_action.schema.json):

```json
{
  "thought": "Reasoning explaining why this specific action was planned",
  "action_type": "create_scene" | "edit_scene" | "delete_scene" | "create_or_update_script" | "create_or_update_scene" | "read_file" | "list_project_files" | "run_project" | "chat_response",
  "parameters": {
    "file_path": "scenes/player.tscn",
    "root_node_name": "Player",
    "root_node_type": "CharacterBody2D",
    "content": "Full modern Godot 4 GDScript code or TSCN definition",
    "script_path": "res://scripts/player.gd",
    "overwrite": false,
    "add_nodes": [
      { "name": "CollisionShape2D", "type": "CollisionShape2D", "parent": "." }
    ],
    "remove_nodes": [],
    "command": "--headless --path .",
    "message": "Conversational reply"
  }
}
```

---

## 📊 Benchmark Results

Evaluated against comprehensive gameplay mechanics and engine integration tests in [`reports/model_eval_benchmark.json`](reports/model_eval_benchmark.json):

| Test ID | Benchmark Category | Score | Latency | Key Criteria Evaluated |
| :--- | :--- | :--- | :--- | :--- |
| **T1_MECHANICS** | 2D Kinematic Controller | **100 / 100** | 15.98s | Velocity, gravity, `move_and_slide`, floor detection, friction, double jump, wall slide. |
| **T2_ACTION_JSON** | Autonomous Scene & Node Generation | **100 / 100** | 4.69s | Schema compliance, node hierarchy, correct `.tscn` root node and children. |
| **T3_POWERUP_LOGIC** | Shield & Invulnerability Mechanic | **75 / 100** | 2.85s | Signal emission (`emit_signal`), shader parameters, state toggles. |
| **T4_ENGINE_API** | Godot 4 API Awareness (Signals & Timers) | **85 / 100** | 1.85s | Modern signal binding, one-shot timers, node tree insertion. |
| **OVERALL** | **Full System Evaluation** | **90.0% (360/400)** | **6.34s avg** | **Production-ready autonomous game development.** |

---

## 🚀 Quickstart Guide

### 1. Prerequisites
* **Python**: `3.10+` or `3.12+` with virtual environment (`.venv`)
* **Node.js**: `v20+` or `v22+` (for Desktop IDE)
* **Godot Engine**: Godot 4.x installed (e.g. `godot4` in PATH)
* **GPU**: NVIDIA GPU with CUDA support (recommended for 4-bit local inference; CPU inference also supported)

### 2. Start the Agent Server
```bash
# Activate your environment
source .venv/bin/activate

# Launch the Godot AI Agent Server
python godot_agent_server.py --port 8000 --device auto
```

### 3. Launch the Desktop IDE
```bash
cd desktop_app

# Install dependencies (first time only)
npm install

# Run Desktop IDE in development mode
npm run electron:dev
```

### 4. Interactive CLI Chat (Terminal Mode)
```bash
# Chat directly with the agent from your command line
python godot_chat.py --project-path /path/to/your/godot_project
```

### 5. In-Engine Godot Plugin Setup
1. Copy `desktop_app/godot_plugin/addons/godot_ai_agent` into your Godot project's `addons/` directory.
2. In Godot 4: navigate to **Project -> Project Settings -> Plugins** and enable **Godot AI Agent**.
3. The plugin will automatically connect to your local server on `http://127.0.0.1:8000`.

---

## 🧪 Training & Data Pipeline

### Fine-Tuning on GPU / DGX
```bash
# Launch QLoRA 4-bit fine-tuning
python train_dgx.py
```

### Running the ETL Pipeline
```bash
# Run data extraction, cleaning, and validation
python -m logic_pipeline.cli --full-pipeline
```

### Running the Evaluation Benchmark
```bash
# Run the automated model benchmark harness
python scripts/eval_benchmark.py --output reports/model_eval_benchmark.json
```

---

## 🛡️ Security & Atomic Rollbacks

* **Path Sandboxing**: The server rejects any paths attempting directory traversal (`../`) or symlink escapes outside the target Godot project root.
* **Atomic Snapshots**: Before executing any file or scene modification, the system writes a `.agent_backup` snapshot.
* **One-Click Reversible Diff**: Any change made by the agent can be previewed as a unified diff and rolled back atomically with zero data loss.

---

## 📄 License
This project is licensed under the MIT License.
