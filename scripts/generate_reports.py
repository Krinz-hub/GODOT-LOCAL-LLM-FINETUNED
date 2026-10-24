import json
from pathlib import Path

jsonl_path = Path("/home/piet/Documents/dataset/reports/prompt_experiments.jsonl")
md_path = Path("/home/piet/Documents/dataset/reports/prompt_experiments.md")

experiments = []
with open(jsonl_path, "r") as f:
    for line in f:
        line = line.strip()
        if line:
            experiments.append(json.loads(line))

md = []
md.append("# DEADZONE: Four Waves — Prompt Engineering Experiment Ledger\n\n")
md.append("## Objective\nSystematically evaluate which types of prompts produce the best results from our custom Godot AI model (`Qwen2.5-Coder-7B-Instruct` + `godot-agent-lora`) while building the Godot game *DEADZONE: Four Waves*.\n\n")
md.append("---\n\n## Model & Infrastructure Baseline\n")
md.append("- **Base Model**: `Qwen/Qwen2.5-Coder-7B-Instruct`\n")
md.append("- **Adapter**: `godot-agent-lora/final_adapter` (PEFT LoRA rank 16, alpha 32)\n")
md.append("- **Inference Server**: `godot_agent_server.py` (Local HTTP Server, port 8000)\n")
md.append("- **Device**: NVIDIA GB10 (121.7 GB VRAM, CUDA 13.0)\n")
md.append("- **Target Project**: `/home/piet/Documents/godot/zombies`\n")
md.append("- **Engine Executable**: Godot 4.7.2 (`/home/piet/.local/bin/godot4`)\n\n---\n")

md.append("## Experiment Summary Table\n\n")
md.append("| Exp ID | Timestamp | Phase | Feature | Prompt Category | Outcome | Regressions | Total Score (/30) |\n")
md.append("|---|---|---|---|---|---|---|---|\n")

for exp in experiments:
    eid = exp.get("experiment_id", "")
    ts = exp.get("timestamp", "").replace("T", " ").replace("Z", "")
    ph = exp.get("phase", "")
    feat = exp.get("feature", "").split("(")[0].strip()
    cat = exp.get("prompt_category", "")
    out = exp.get("outcome", "").capitalize()
    reg = exp.get("regression_count", 0)
    score = exp.get("scores", {}).get("total", "N/A")
    md.append(f"| {eid} | {ts} | {ph} | {feat} | {cat} | {out} | {reg} | {score}/30 |\n")

md.append("\n---\n\n## Detailed Experiment Logs\n\n")

for exp in experiments:
    eid = exp.get("experiment_id", "")
    ts = exp.get("timestamp", "")
    ph = exp.get("phase", "")
    feat = exp.get("feature", "")
    cat = exp.get("prompt_category", "")
    scores = exp.get("scores", {})
    intended = exp.get("intended_result", "")
    context = exp.get("context_supplied", "")
    actual = exp.get("actual_output", "")
    files = json.dumps(exp.get("files_changed", []))
    outcome = exp.get("outcome", "").capitalize()
    lessons = exp.get("lessons_learned", "")
    
    s_corr = scores.get("requirement_correctness", "N/A")
    s_int = scores.get("integration_quality", "N/A")
    s_test = scores.get("test_performance", "N/A")
    s_eff = scores.get("correction_efficiency", "N/A")
    s_scope = scores.get("scope_discipline", "N/A")
    s_godot = scores.get("godot_correctness", "N/A")
    s_total = scores.get("total", "N/A")

    md.append(f"### {eid}: {feat}\n")
    md.append(f"- **Timestamp**: {ts}\n")
    md.append(f"- **Game Phase**: {ph}\n")
    md.append(f"- **Prompt Category**: {cat}\n")
    md.append(f"- **Intended Result**: {intended}\n")
    md.append(f"- **Context Supplied**: {context}\n")
    md.append(f"- **Actual Output**: {actual}\n")
    md.append(f"- **Files Changed**: `{files}`\n")
    md.append(f"- **Scores**: Correctness: {s_corr}/5 | Integration: {s_int}/5 | Tests: {s_test}/5 | Efficiency: {s_eff}/5 | Scope: {s_scope}/5 | Godot: {s_godot}/5 | **Total: {s_total}/30**\n")
    md.append(f"- **Outcome**: {outcome}\n")
    md.append(f"- **Lessons Learned**: {lessons}\n\n")

md_path.write_text("".join(md))
print(f"Successfully generated {md_path} with {len(experiments)} experiments")
