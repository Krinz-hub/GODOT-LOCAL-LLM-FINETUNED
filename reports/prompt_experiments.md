# DEADZONE: Four Waves — Prompt Engineering Experiment Ledger

## Objective
Systematically evaluate which types of prompts produce the best results from our custom Godot AI model (`Qwen2.5-Coder-7B-Instruct` + `godot-agent-lora`) while building the Godot game *DEADZONE: Four Waves*.

---

## Model & Infrastructure Baseline
- **Base Model**: `Qwen/Qwen2.5-Coder-7B-Instruct`
- **Adapter**: `godot-agent-lora/final_adapter` (PEFT LoRA rank 16, alpha 32)
- **Inference Server**: `godot_agent_server.py` (Local HTTP Server, port 8000)
- **Device**: NVIDIA GB10 (121.7 GB VRAM, CUDA 13.0)
- **Target Project**: `/home/piet/Documents/godot/zombies`
- **Engine Executable**: Godot 4.7.2 (`/home/piet/.local/bin/godot4`)

---
## Experiment Summary Table

| Exp ID | Timestamp | Phase | Feature | Prompt Category | Outcome | Regressions | Total Score (/30) |
|---|---|---|---|---|---|---|---|
| EXP-000 | 2026-10-23 12:54:51 | Phase 0 | Model Health / Connectivity | Minimal | Passed | 0 | 30/30 |
| EXP-001 | 2026-10-23 13:18:20 | Phase 1 | Player Controller | Detailed | Partially passed | 0 | 20/30 |
| EXP-002 | 2026-10-23 13:19:47 | Phase 1 | Player Controller Fix | Correction | Failed | 1 | 7/30 |
| EXP-003 | 2026-10-23 13:20:32 | Phase 1 | Complete Standalone Player Controller | Detailed / Clean Functional Specification | Passed | 0 | 25/30 |
| EXP-004 | 2026-10-23 13:22:08 | Phase 1 | Project Configuration | Detailed | Passed | 0 | 30/30 |
| EXP-005 | 2026-10-23 13:23:10 | Phase 1 | Player Controller with Mouse Aim and Knife | Detailed | Failed | 1 | 13/30 |
| EXP-006 | 2026-10-23 13:44:00 | Phase 1 | Autoload State Manager | Detailed / Scene-Tree Context | Passed | 0 | 30/30 |
| EXP-007 | 2026-10-23 13:46:10 | Phase 1 | Projectile Logic | Detailed / Scene-Tree Context | Passed | 0 | 30/30 |
| EXP-008 | 2026-10-23 13:50:00 | Phase 1 | Player Controller & Scene Assembly | Correction & QA Refinement | Passed | 0 | 30/30 |
| EXP-009 | 2026-10-23 13:52:00 | Phase 2 | Zombie Enemy AI State Machine | Detailed / Scene-Tree Context | Passed | 0 | 30/30 |
| EXP-011 | 2026-10-23 13:54:00 | Phase 4 | Safe House Weapon Upgrade Bench | Detailed / UI Architecture Refinement | Passed | 0 | 30/30 |
| EXP-012 | 2026-10-23 13:56:00 | Phase 5 | Wave Director, HUD Controller & Arena Assembly | Detailed / Scene-Tree Context | Passed | 0 | 30/30 |
| EXP-013 | 2026-10-23 14:12:00 | User Refinement | Mouse-Facing Relative Player Movement | Refinement / Vector Math Specification | Passed | 0 | 30/30 |
| EXP-014 | 2026-10-23 14:13:00 | User Refinement | HUD Radar Minimap | Detailed / Canvas Item Drawing | Passed | 0 | 30/30 |
| EXP-015 | 2026-10-23 14:58:00 | Asset Integration | Sprite Graphics & Sound FX Integration | Detailed / Asset Pipeline Integration | Passed | 0 | 30/30 |
| EXP-016 | 2026-10-23 15:08:00 | Environment Polish | Non-Repetitive Grassy Foliage Environment | Procedural Organic Generation | Passed | 0 | 30/30 |
| EXP-017 | 2026-10-23 15:18:00 | Editor & Visual Polish | Direct Scene Foliage & Terrain Assembly | Direct Scene Node Architecture | Passed | 0 | 30/30 |
| EXP-018 | 2026-10-23 15:25:00 | Combat Juiciness & FX | Killing Animations, Blood Splatter & Permanent Ground Decals | Juicy Combat & Visual Feedback | Passed | 0 | 30/30 |
| EXP-019 | 2026-10-23 15:48:00 | Combat Juiciness & FX | Knife Slash Animation & Audio Swoosh | Melee Combat FX & Animation Tweens | Passed | 0 | 29/30 |

---

## Detailed Experiment Logs

### EXP-000: Model Health / Connectivity
- **Timestamp**: 2026-10-23T12:54:51Z
- **Game Phase**: Phase 0
- **Prompt Category**: Minimal
- **Intended Result**: Verify model loads and returns valid GodotAgentAction JSON
- **Context Supplied**: SYSTEM_ACTION_PROMPT
- **Actual Output**: {"thought": "The user requested a test connection. I will respond with a simple message indicating that the model is ready.", "action_type": "chat_response", "parameters": {"message": "Model is ready."}}
- **Files Changed**: `[]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: Model outputs clean JSON schema without unwanted chat text.

### EXP-001: Player Controller (scripts/player.gd)
- **Timestamp**: 2026-10-23T13:18:20Z
- **Game Phase**: Phase 1
- **Prompt Category**: Detailed
- **Intended Result**: Fully working Godot 4 player controller with 8-way movement, dodge, stamina, and health
- **Context Supplied**: Default system prompt + project tree
- **Actual Output**: Created scripts/player.gd (3397 bytes)
- **Files Changed**: `["scripts/player.gd"]`
- **Scores**: Correctness: 3/5 | Integration: 3/5 | Tests: 3/5 | Efficiency: 3/5 | Scope: 5/5 | Godot: 3/5 | **Total: 20/30**
- **Outcome**: Partially passed
- **Lessons Learned**: Detailed prompt without explicit method signature resulted in missing take_damage. Needs precise correction prompt specifying state logic for dodge and stamina.

### EXP-002: Player Controller Fix (scripts/player.gd)
- **Timestamp**: 2026-10-23T13:19:47Z
- **Game Phase**: Phase 1
- **Prompt Category**: Correction
- **Intended Result**: Fix missing take_damage and logic defects in scripts/player.gd
- **Context Supplied**: Default system prompt + project context
- **Actual Output**: Model entered repetition loop in _ready() checking for non-existent Camera and Inventory nodes, hit max_tokens, JSON truncated and recovered by regex.
- **Files Changed**: `["scripts/player.gd"]`
- **Scores**: Correctness: 1/5 | Integration: 1/5 | Tests: 1/5 | Efficiency: 1/5 | Scope: 2/5 | Godot: 1/5 | **Total: 7/30**
- **Outcome**: Failed
- **Lessons Learned**: Complex multi-defect correction prompts trigger model hallucination and token degeneration loops. Narrow, step-by-step or clean-slate structured specification prompts are much more reliable than diff-style defect lists.

### EXP-003: Complete Standalone Player Controller (scripts/player.gd)
- **Timestamp**: 2026-10-23T13:20:32Z
- **Game Phase**: Phase 1
- **Prompt Category**: Detailed / Clean Functional Specification
- **Intended Result**: Clean, valid GDScript player controller without hallucinations or infinite loops
- **Context Supplied**: Exact class, properties, signals, method signatures, and constraints
- **Actual Output**: Successfully generated clean scripts/player.gd (1586 bytes)
- **Files Changed**: `["scripts/player.gd"]`
- **Scores**: Correctness: 4/5 | Integration: 4/5 | Tests: 4/5 | Efficiency: 4/5 | Scope: 5/5 | Godot: 4/5 | **Total: 25/30**
- **Outcome**: Passed
- **Lessons Learned**: Clean functional specification with exact method signatures completely eliminated hallucinated dependencies and repetition loops. High-fidelity output.

### EXP-004: Project Configuration (project.godot)
- **Timestamp**: 2026-10-23T13:22:08Z
- **Game Phase**: Phase 1
- **Prompt Category**: Detailed
- **Intended Result**: Update project.godot to Godot 4 format so godot4 headless engine can validate and run scenes
- **Context Supplied**: Godot 4 config requirements, window resolution, physics layers
- **Actual Output**: Written project.godot (434 bytes)
- **Files Changed**: `["project.godot"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: Model formatted project.godot accurately with all requested 2D viewport, physics layer, and main scene settings.

### EXP-005: Player Controller with Mouse Aim and Knife (scripts/player.gd)
- **Timestamp**: 2026-10-23T13:23:10Z
- **Game Phase**: Phase 1
- **Prompt Category**: Detailed
- **Intended Result**: Update player controller with mouse aim and melee knife attack
- **Context Supplied**: Godot 4 mouse look_at, knife attack Area2D check, dodge cooldown
- **Actual Output**: Written scripts/player.gd (2634 bytes), but contained stray backslashes before variable names on lines 52, 55, 56, 57
- **Files Changed**: `["scripts/player.gd"]`
- **Scores**: Correctness: 3/5 | Integration: 2/5 | Tests: 0/5 | Efficiency: 2/5 | Scope: 5/5 | Godot: 1/5 | **Total: 13/30**
- **Outcome**: Failed
- **Lessons Learned**: The model introduced stray backslashes before dodge variables when generating assignments in an unindented block.

### EXP-006: Autoload State Manager (scripts/globals.gd)
- **Timestamp**: 2026-10-23T13:44:00Z
- **Game Phase**: Phase 1
- **Prompt Category**: Detailed / Scene-Tree Context
- **Intended Result**: Generate complete, functional Autoload Globals singleton for currency, waves, weapons, and signals
- **Context Supplied**: Scene Tree context prompt with functional requirements
- **Actual Output**: Successfully generated 2402 bytes of valid Godot 4 GDScript without syntax errors
- **Files Changed**: `["scripts/globals.gd", "project.godot"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: Scene-Tree formatted prompt with explicit functional requirements produced flawless Godot 4 autoload script on first attempt.

### EXP-007: Projectile Logic (scripts/bullet.gd)
- **Timestamp**: 2026-10-23T13:46:10Z
- **Game Phase**: Phase 1
- **Prompt Category**: Detailed / Scene-Tree Context
- **Intended Result**: Working projectile script with movement, lifetime timer, and damage collision
- **Context Supplied**: Scene-tree and signal connection requirements
- **Actual Output**: Generated valid Godot 4 GDScript using signal connect and transform.x translation
- **Files Changed**: `["scripts/bullet.gd"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: Model generated modern Godot 4 signal connection syntax (body_entered.connect) flawlessly.

### EXP-008: Player Controller & Scene Assembly (scripts/player.gd, scenes/player.tscn)
- **Timestamp**: 2026-10-23T13:50:00Z
- **Game Phase**: Phase 1
- **Prompt Category**: Correction & QA Refinement
- **Intended Result**: Generate 100% compliant Godot 4 player controller with full weapons, aiming, stamina, dodge, and damage mechanics
- **Context Supplied**: Scene-tree context, exact node hierarchy, strict Godot 4 syntax rules prohibiting Godot 3 setget/update regressions
- **Actual Output**: Generated flawless 3837-byte GDScript, paired with scenes/player.tscn, verified in Godot 4 with exit code 0
- **Files Changed**: `["scripts/player.gd", "scenes/player.tscn", "scripts/globals.gd"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: Explicitly forbidding legacy Godot 3 syntax (setget, update) prevented model regressions and produced a perfect Godot 4 controller.

### EXP-009: Zombie Enemy AI State Machine (scripts/zombie.gd, scenes/zombie.tscn)
- **Timestamp**: 2026-10-23T13:52:00Z
- **Game Phase**: Phase 2
- **Prompt Category**: Detailed / Scene-Tree Context
- **Intended Result**: Generate working zombie enemy with pursuit, telegraph attack, damage taken tween, and death coin rewards
- **Context Supplied**: Full scene-tree structure, state machine specifications, visual telegraph parameters
- **Actual Output**: Generated 3475-byte state machine script, cleanly validated with scenes/zombie.tscn in Godot 4 (exit code 0)
- **Files Changed**: `["scripts/zombie.gd", "scenes/zombie.tscn"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: Specifying state transitions and timer hooks resulted in a complete, self-contained enemy AI on first full generation.

### EXP-011: Safe House Weapon Upgrade Bench (scripts/upgrade_station.gd, scenes/upgrade_station.tscn)
- **Timestamp**: 2026-10-23T13:54:00Z
- **Game Phase**: Phase 4
- **Prompt Category**: Detailed / UI Architecture Refinement
- **Intended Result**: Working safe house upgrade station allowing player to browse, buy, and equip weapons with currency
- **Context Supplied**: Scene-tree context, exact node hierarchy, Control UI parentage constraint
- **Actual Output**: Clean 3082-byte script paired with scenes/upgrade_station.tscn, validated in Godot 4 with exit code 0
- **Files Changed**: `["scripts/upgrade_station.gd", "scenes/upgrade_station.tscn"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: Model attempted to call Control theme methods on Area2D; explicitly requiring clean Control hierarchy in prompt resolved the issue immediately.

### EXP-012: Wave Director, HUD Controller & Arena Assembly (scripts/game_manager.gd, scenes/main.tscn)
- **Timestamp**: 2026-10-23T13:56:00Z
- **Game Phase**: Phase 5
- **Prompt Category**: Detailed / Scene-Tree Context
- **Intended Result**: Complete playable arena game orchestrating wave spawns, player death, intermission countdown, and victory
- **Context Supplied**: Full scene-tree context, exact wave tuning parameters, HUD node hierarchy
- **Actual Output**: Generated 4867-byte wave manager script and validated scenes/main.tscn in Godot 4 headless with exit code 0
- **Files Changed**: `["scripts/game_manager.gd", "scenes/main.tscn"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: End-to-end game manager script generated with accurate state transitions and dynamic wave scaling.

### EXP-013: Mouse-Facing Relative Player Movement (scripts/player.gd)
- **Timestamp**: 2026-10-23T14:12:00Z
- **Game Phase**: User Refinement
- **Prompt Category**: Refinement / Vector Math Specification
- **Intended Result**: Player moves forward directly toward mouse cursor on W/Up, strafes on A/D
- **Context Supplied**: Scene tree context, vector math specification for mouse-relative translation, Godot 4 syntax rules
- **Actual Output**: Generated 4079-byte player controller with mouse-relative orientation, verified with Godot 4 headless exit code 0
- **Files Changed**: `["scripts/player.gd"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: Specifying the exact forward/right orthogonal vector math in the prompt ensured the model implemented smooth mouse-relative movement on the first try.

### EXP-014: HUD Radar Minimap (scripts/minimap.gd, scenes/main.tscn)
- **Timestamp**: 2026-10-23T14:13:00Z
- **Game Phase**: User Refinement
- **Prompt Category**: Detailed / Canvas Item Drawing
- **Intended Result**: Functional radar minimap anchored in lower-left corner showing arena bounds, safehouse, live player, and live zombies
- **Context Supplied**: Scene tree context, world coordinate mapping bounds (-500 to 2500 X, -500 to 2000 Y), canvas draw primitives
- **Actual Output**: Generated 1719-byte minimap script, added Minimap node under HUD in scenes/main.tscn, validated in Godot 4 with exit code 0
- **Files Changed**: `["scripts/minimap.gd", "scenes/main.tscn"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: Model generated canvas draw primitives cleanly. Correcting Rect2 size argument ensured accurate safehouse rendering.

### EXP-015: Sprite Graphics & Sound FX Integration (Player, Zombie, Bench, Gunshot, Hit, Click)
- **Timestamp**: 2026-10-23T14:58:00Z
- **Game Phase**: Asset Integration
- **Prompt Category**: Detailed / Asset Pipeline Integration
- **Intended Result**: Replace all prototype Polygon2D visuals with production 2D top-down sprites and dynamic sound effects
- **Context Supplied**: Kenney CC0 Topdown Shooter sprite assets, audio streams, Sprite2D and AudioStreamPlayer2D node hierarchies
- **Actual Output**: Successfully integrated player weapon-swapping sprites, zombie animated textures, gunshot audio, impact audio, and UI click audio. Tested in Godot 4 with clean exit code 0.
- **Files Changed**: `["assets/sprites/player/", "assets/sprites/zombie/", "assets/sprites/weapons/", "assets/sprites/environment/", "assets/sounds/", "scripts/player.gd", "scenes/player.tscn", "scripts/zombie.gd", "scenes/zombie.tscn", "scenes/upgrade_station.tscn"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: When adding new raw image and audio files, Godot requires running editor import scan (--editor --quit) so resources are compiled into .godot/imported/ before scene loading.

### EXP-016: Non-Repetitive Grassy Foliage Environment (scripts/environment_generator.gd, scenes/main.tscn)
- **Timestamp**: 2026-10-23T15:08:00Z
- **Game Phase**: Environment Polish
- **Prompt Category**: Procedural Organic Generation
- **Intended Result**: Rich organic grassy environment with trees, bushes, rocks, and soft ground color variations without repetitive tile patterns
- **Context Supplied**: Full scene tree context, arena dimensions (-300 to 2300 X, -300 to 1800 Y), safehouse exclusion boundary, foliage asset textures
- **Actual Output**: Generated 4264-byte procedural foliage generator script, updated main arena with meadow grass terrain, verified in Godot 4 with exit code 0
- **Files Changed**: `["scripts/environment_generator.gd", "scenes/main.tscn", "assets/sprites/environment/"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: Combining procedural scattering of diverse tree/bush/rock sprites with randomized multi-tinted terrain glades eliminated grid repetition and produced a vibrant natural arena.

### EXP-017: Direct Scene Foliage & Terrain Assembly (scenes/main.tscn)
- **Timestamp**: 2026-10-23T15:18:00Z
- **Game Phase**: Editor & Visual Polish
- **Prompt Category**: Direct Scene Node Architecture
- **Intended Result**: Render all trees, bushes, rocks, and grass tufts directly in the Godot 2D editor viewport without requiring Play mode
- **Context Supplied**: Full Godot 4 TSCN scene format, 170+ explicit environmental nodes with CollisionShape2D and Sprite2D instances, non-repetitive scale/rotation/tint distributions
- **Actual Output**: Successfully generated 1661-line scenes/main.tscn containing 170+ explicit foliage nodes, validated in Godot 4 with exit code 0
- **Files Changed**: `["scenes/main.tscn"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: Procedural generation in runtime _ready() leaves editor viewports blank. Defining environmental foliage directly as scene nodes ensures immediate visual fidelity in the editor and interactive designer manipulation.

### EXP-018: Killing Animations, Blood Splatter & Permanent Ground Decals (scripts/zombie.gd, scenes/zombie.tscn, scripts/player.gd)
- **Timestamp**: 2026-10-23T15:25:00Z
- **Game Phase**: Combat Juiciness & FX
- **Prompt Category**: Juicy Combat & Visual Feedback
- **Intended Result**: High-impact, dramatic death sequence with blood splatter particles, ground blood stains, and squash/spin tween animations instead of abrupt disappearance
- **Context Supplied**: Existing zombie.gd take_damage() and die() flow, CPUParticles2D configuration, blood decal sprite path, Tween API in Godot 4
- **Actual Output**: Clean Godot 4 implementation in scripts/zombie.gd with CPUParticles2D in scenes/zombie.tscn, and dramatic collapse with blood puddle in scripts/player.gd. Verified headless with exit code 0.
- **Files Changed**: `["scripts/zombie.gd", "scenes/zombie.tscn", "scripts/player.gd"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 5/5 | Scope: 5/5 | Godot: 5/5 | **Total: 30/30**
- **Outcome**: Passed
- **Lessons Learned**: Using set_deferred("collision_layer", 0) prevents dead corpses from acting as invisible walls during death tweens. Combining CPUParticles2D bursts with permanent ground Sprite2D decals creates visceral, enduring battlefield feedback.

### EXP-019: Knife Slash Animation & Audio Swoosh (scripts/player.gd, scenes/player.tscn)
- **Timestamp**: 2026-10-23T15:48:00Z
- **Game Phase**: Combat Juiciness & FX
- **Prompt Category**: Melee Combat FX & Animation Tweens
- **Intended Result**: Crisp visual crescent slash animation, sound effect, and player sprite thrust when attacking with knife
- **Context Supplied**: Node hierarchy with SlashSound (AudioStreamPlayer2D) and SlashSprite (Sprite2D with slash_arc.png), Godot 4 Tween API
- **Actual Output**: Clean Godot 4 perform_melee_attack() method with parallel tweened slash arc, micro-lunge recoil, and audio trigger. Tested in Godot 4 with exit code 0.
- **Files Changed**: `["scripts/player.gd", "scenes/player.tscn", "assets/sprites/effects/slash_arc.png", "assets/sounds/knife_slash.wav"]`
- **Scores**: Correctness: 5/5 | Integration: 5/5 | Tests: 5/5 | Efficiency: 4/5 | Scope: 5/5 | Godot: 5/5 | **Total: 29/30**
- **Outcome**: Passed
- **Lessons Learned**: Targeted method-level prompts with exact node context prevent the model from hallucinating inventory arrays or token truncating on complex controller scripts.

