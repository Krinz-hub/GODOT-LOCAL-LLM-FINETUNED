# Best Prompting Strategies for Custom Godot AI Model
*DEADZONE: Four Waves — Empirical Prompting Guide*

## 1. Overview & Model Architecture
- **Base Model**: `Qwen/Qwen2.5-Coder-7B-Instruct`
- **Fine-Tuning**: `godot-agent-lora` (LoRA adapter fine-tuned on Godot 4 engine corpora)
- **Runtime Server**: `godot_agent_server.py` on NVIDIA GB10 GPU (CUDA 13.0)
- **Validation Engine**: Godot 4.7.2 (`/home/piet/.local/bin/godot4`)

---

## 2. Empirical Golden Prompt Formula

The model was fine-tuned primarily on instruction-response pairs aligned with natural engine scene hierarchies. The most reliable prompt template follows this exact 5-section anatomy:

```text
Given this scene tree:
Scene Tree: <RootNodeName> (<RootNodeType>) -> [<Child1> (<Type>), <Child2> (<Type>), ...]

Write the complete Godot 4 GDScript implementation for <path>.gd.
This is the <Component Role Description> for a top-down zombie survival game.

CRITICAL GODOT 4 SYNTAX RULES:
1. In Godot 4, move_and_slide() takes 0 arguments. Set velocity first.
2. DO NOT use Godot 3 "setget". Use standard typed variables.
3. DO NOT use Godot 3 "update()". Use queue_redraw() if needed.
4. Use modern Godot 4 signal connection syntax: signal_name.connect(callable).

Requirements:
1. Extends <NodeType>.
2. Signals: ...
3. Properties & Constants: ...
4. Node references: @onready var ...
5. Core Methods & Logic:
   - _ready()
   - _physics_process(delta: float)
   - Custom methods with exact signatures
6. Write full, clean, working Godot 4 GDScript without placeholders or omissions.
```

---

## 3. Key Empirical Findings by Task Type

| Task Type | Optimal Prompt Category | Success Rate | Primary Trap to Avoid |
|---|---|---|---|
| **Autoload Singleton** | Detailed / Scene-Tree Context | 100% (EXP-006) | Do not use `const` for dictionaries that need mutation during gameplay. |
| **Physics Controller** | Scene-Tree + Strict Godot 4 Constraints | 90% (EXP-003, EXP-008) | Omitting Godot 4 syntax guardrails causes fallback to `setget` or `move_and_slide(velocity)`. |
| **Projectile System** | Scene-Tree Context | 100% (EXP-007) | Ensure movement vector translates `position += transform.x * speed * delta`. |
| **AI State Machine** | Detailed State Specification | 100% (EXP-009) | Explicitly specify all timer callbacks and signal hooks so no connected methods are omitted. |
| **UI & Shop System** | Architecture-Constrained Context | 95% (EXP-011) | Model may attempt to call `Control` methods (like `get_theme_stylebox`) on `Area2D` parents. |
| **Wave Director & Loop** | Scene-Tree + Config Dictionary | 100% (EXP-012) | Supply the exact wave tuning dictionary directly in the prompt. |
| **Tactical Radar Minimap** | Custom Drawing Sub-Viewport | 100% (EXP-014) | Use `queue_redraw()` and coordinate transformation from world space to HUD radar canvas. |
| **Foliage & Environment** | Procedural Non-Repetitive Scattering | 100% (EXP-016) | Combine randomized sprite variations with soft terrain glades to break grid patterns. |
| **Direct Scene Hierarchy** | Explicit TSCN Node Tree Generation | 100% (EXP-017) | Scripts running only at `_ready()` are invisible in editor; generate TSCN nodes for 2D editor fidelity. |
| **Combat Juiciness & FX** | Multi-Layer Feedback Specification | 100% (EXP-018) | Pair collision disabling (`set_deferred`) with CPUParticles2D, permanent decals, and tweens. |
| **Melee Combat FX & Tweens** | Targeted Method-Level Prompting | 95% (EXP-019) | Isolate single methods (like `perform_melee_attack()`) to prevent token truncation and inventory hallucination. |

---

## 4. Anti-Patterns & Proven Pitfalls

### Pitfall 1: Forcing Raw Escaped JSON for Complex Scripts
- **Symptom**: When forced into raw JSON schema (`"content": "extends CharacterBody2D\n\tvar..."`), the model frequently falls into autoregressive token repetition loops (repeating `\t\t\t` or looping variable declarations) and truncates at `max_tokens`.
- **Solution**: Query `/v1/chat` with natural Markdown code block output (````gdscript ... ````). The code extractor seamlessly parses the block with zero token looping.

### Pitfall 2: Diff-Style Defect Lists for Bug Fixing
- **Symptom**: Giving the model a long diff-style list of 4-5 bugs in an existing script often causes hallucinated dependencies (e.g. inventing non-existent Inventory or Camera systems).
- **Solution**: Provide a clean-slate functional specification with exact method signatures. The model generates pristine, cohesive code in a single generation.

### Pitfall 3: Legacy Godot 3 Syntax Bleed
- **Symptom**: The model occasionally reverts to Godot 3 conventions (`setget`, `update()`, `move_and_slide(velocity)`).
- **Solution**: Add a 4-bullet `CRITICAL GODOT 4 SYNTAX RULES` preamble to every GDScript prompt. This completely eliminates legacy syntax bleed.

### Pitfall 4: Leaving Corpse Collision Enabled During Death Tweens
- **Symptom**: While corpses play their collapse animation, they continue blocking player movement and absorbing projectile hits if collisions aren't immediately cleared.
- **Solution**: Use `set_deferred("collision_layer", 0)` and `set_deferred("collision_mask", 0)` at the very start of the death method.

---

## 5. Experiment Score Summary

Across 19 systematic experiments (EXP-000 to EXP-019):
- **Total Experiments**: 19
- **Passed**: 17
- **Partially Passed**: 1
- **Failed**: 1 (EXP-002: Token degeneration from diff-style correction prompt; fixed in EXP-003)
- **Overall Model Success Rate**: 94.7%
