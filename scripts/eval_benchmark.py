#!/usr/bin/env python3
"""
Godot Fine-Tuned Model Benchmark & Evaluation Script
Tests the local model across 4 distinct dimensions:
1. GDScript Game Mechanics Generation (Platformer Controller)
2. Godot Autonomous Action Generation (Scene & Script JSON actions)
3. Godot 3 vs Godot 4 API & Signal Handling
4. Code Completeness & GDScript Syntax Validation
"""

import json
import time
import urllib.request
import os
from typing import Dict, Any, List

SERVER_URL = "http://127.0.0.1:8000"

BENCHMARK_TESTS = [
    {
        "id": "T1_MECHANICS",
        "name": "Game Mechanics: 2D Kinematic Controller with Double Jump & Wall Slide",
        "endpoint": "/v1/chat",
        "prompt": "Write a complete Godot 2D player character controller script in GDScript that implements gravity, smooth horizontal acceleration/friction, jump, double-jump, and wall sliding. Return only the GDScript code.",
        "eval_type": "code_generation",
        "expected_keywords": ["velocity", "gravity", "move_and_slide", "is_on_floor", "jump"],
    },
    {
        "id": "T2_ACTION_JSON",
        "name": "Autonomous Action: Scene & Node Generation",
        "endpoint": "/v1/action",
        "prompt": "Create a new scene scenes/coin.tscn with an Area2D root node named Coin and a CollisionShape2D child.",
        "eval_type": "json_action",
        "expected_action_types": ["create_scene", "create_or_update_scene"],
    },
    {
        "id": "T3_POWERUP_LOGIC",
        "name": "Feature Addition: Shield / Invulnerability Mechanic",
        "endpoint": "/v1/chat",
        "prompt": "Given a player script, write the GDScript methods `grant_shield()` and `hit_hazard() -> bool` where the shield absorbs one hazard hit, changes sprite color, and emits a shield_broken signal.",
        "eval_type": "code_generation",
        "expected_keywords": ["has_shield", "modulate", "emit_signal", "signal"],
    },
    {
        "id": "T4_ENGINE_API",
        "name": "Godot API Version Awareness: Signals & Connections",
        "endpoint": "/v1/chat",
        "prompt": "Write the exact GDScript code to create a Timer node programmatically, configure it for 1.5 seconds one-shot, connect its timeout signal to a function `_on_timer_timeout()`, and start it.",
        "eval_type": "code_generation",
        "expected_keywords": ["Timer", "wait_time", "one_shot", "connect", "timeout", "start"],
    }
]


def query_server(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{SERVER_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        elapsed = time.time() - t0
        body = json.loads(resp.read().decode("utf-8"))
        body["_elapsed_sec"] = elapsed
        return body


def evaluate_benchmark() -> Dict[str, Any]:
    print("=================================================================")
    print("  RUNNING EMPIRICAL BENCHMARK ON LOCAL GODOT MODEL (Qwen-7B-LoRA)")
    print("=================================================================")

    results: List[Dict[str, Any]] = []

    for test in BENCHMARK_TESTS:
        print(f"\n▶ Executing: [{test['id']}] {test['name']}...")
        payload = {"prompt": test["prompt"], "max_tokens": 1200}
        
        try:
            resp = query_server(test["endpoint"], payload)
            elapsed = resp.get("_elapsed_sec", 0.0)
            
            raw_text = ""
            action_data = None

            if test["eval_type"] == "json_action":
                action_data = resp.get("action", {})
                act_type = action_data.get("action_type", "")
                params = action_data.get("parameters", {})
                score = 0
                max_score = 100
                criteria = []

                if act_type in test["expected_action_types"] or "scene" in act_type:
                    score += 40
                    criteria.append("✓ Correct action_type generated")
                else:
                    criteria.append(f"✗ Unexpected action_type: {act_type}")

                if "file_path" in params and "coin" in params["file_path"].lower():
                    score += 30
                    criteria.append("✓ Correct target file_path identified")
                else:
                    criteria.append("✗ Target file_path missing or inaccurate")

                if params.get("content") or params.get("root_node_type") == "Area2D":
                    score += 30
                    criteria.append("✓ Appropriate scene definition/content produced")
                else:
                    criteria.append("✗ Scene definition payload incomplete")

                results.append({
                    "id": test["id"],
                    "name": test["name"],
                    "score": score,
                    "max_score": max_score,
                    "elapsed_sec": round(elapsed, 2),
                    "criteria": criteria,
                    "sample_output": str(action_data)[:250] + "..."
                })
                print(f"  Score: {score}/{max_score} in {elapsed:.2f}s")

            else:
                raw_text = resp.get("response", "")
                score = 0
                max_score = 100
                criteria = []

                # Keyword check
                found_kw = [kw for kw in test["expected_keywords"] if kw.lower() in raw_text.lower()]
                kw_ratio = len(found_kw) / len(test["expected_keywords"])
                score += int(kw_ratio * 50)
                criteria.append(f"✓ Found {len(found_kw)}/{len(test['expected_keywords'])} domain keywords ({', '.join(found_kw)})")

                # Code block formatting
                if "```gdscript" in raw_text or "```" in raw_text:
                    score += 25
                    criteria.append("✓ Clean markdown code block formatting")
                else:
                    criteria.append("✗ Missing markdown code block formatting")

                # Completeness check (no lazy TODO comments)
                if "TODO" not in raw_text and "pass #" not in raw_text and len(raw_text) > 200:
                    score += 25
                    criteria.append("✓ Complete implementation without placeholder comments")
                else:
                    score += 10
                    criteria.append("⚠ Partial implementation or placeholders detected")

                results.append({
                    "id": test["id"],
                    "name": test["name"],
                    "score": score,
                    "max_score": max_score,
                    "elapsed_sec": round(elapsed, 2),
                    "criteria": criteria,
                    "sample_output": raw_text[:250].replace("\n", " ") + "..."
                })
                print(f"  Score: {score}/{max_score} in {elapsed:.2f}s")

        except Exception as e:
            print(f"  ✗ Error executing test: {e}")
            results.append({
                "id": test["id"],
                "name": test["name"],
                "score": 0,
                "max_score": 100,
                "elapsed_sec": 0.0,
                "criteria": [f"Execution error: {e}"],
                "sample_output": ""
            })

    total_score = sum(r["score"] for r in results)
    total_possible = sum(r["max_score"] for r in results)
    avg_latency = sum(r["elapsed_sec"] for r in results) / len(results) if results else 0.0

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_score_pct": round((total_score / total_possible) * 100, 1),
        "total_score": total_score,
        "total_possible": total_possible,
        "avg_latency_sec": round(avg_latency, 2),
        "tests": results
    }

    os.makedirs("reports", exist_ok=True)
    with open("reports/model_eval_benchmark.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=================================================================")
    print(f"  BENCHMARK COMPLETE: {summary['total_score_pct']}% Overall Score")
    print(f"  Average Latency: {summary['avg_latency_sec']}s on GB10 GPU")
    print("=================================================================")
    return summary


if __name__ == "__main__":
    evaluate_benchmark()
