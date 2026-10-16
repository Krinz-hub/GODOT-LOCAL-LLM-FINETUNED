"""Comprehensive Offline Tests for Godot Project-Logic Extraction Pipeline.

Tests all 13 criteria from Phase 7:
1. Joining project metadata to code records via streaming CodeIndex
2. Missing and duplicate file paths handling
3. Real scene hierarchy extraction (indented lines, root type compliance)
4. Scene-to-script references
5. Autoload and resource references
6. Project graph construction, cycle detection, and missing dependencies
7. Canonical production-logic schema compatibility (canonical.py)
8. Honest handling of missing evidence
9. Debugging records with unverified fixes
10. Project-level dataset splitting without leakage
11. Exporting real records rather than fixture fallbacks
12. Empty input and all-records-rejected behavior
13. Idempotent execution and safe output handling
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Dict, List
import unittest

from logic_pipeline.config import AppConfig, PipelineConfig, SourcesConfig, CleaningRules, ValidationRules
from logic_pipeline.extractors.gdscript import parse_gdscript
from logic_pipeline.extractors.project_config import parse_project_godot
from logic_pipeline.extractors.scene import parse_scene_file
from logic_pipeline.extractors.structured_mappers import (
    map_structured_project_to_production_logic,
    map_structured_debugging_to_repair,
    map_structured_agent_task_to_trajectory,
)
from logic_pipeline.analysis.project_graph import ProjectGraph
from logic_pipeline.analysis.dependency_analysis import analyze_dependencies
from logic_pipeline.sources.structured_ingest import CodeIndex, StructuredIngestionAdapter
from logic_pipeline.validation.canonical import check_canonical_plan
from logic_pipeline.validation.schema import validate_against_schema
from logic_pipeline.processing.split_dataset import split_dataset_by_project
from logic_pipeline.processing.export_training import (
    export_dataset_a_to_sharegpt,
    export_dataset_a_architecture_to_sharegpt,
    export_dataset_b_to_sharegpt,
    export_dataset_c_to_sharegpt,
    export_to_sharegpt,
)
from logic_pipeline.cli import cmd_export


class TestCanonicalPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace_root = Path(__file__).resolve().parents[2]
        cls.structured_dir = cls.workspace_root / "structured"
        cls.projects_file = cls.structured_dir / "projects.jsonl"
        cls.code_file = cls.structured_dir / "code.jsonl"
        cls.debugging_file = cls.structured_dir / "debugging.jsonl"

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="godot_pipeline_test_")
        self.test_path = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Joining project metadata to code records
    # -------------------------------------------------------------------------
    def test_01_joining_metadata_to_code(self):
        """Test streaming CodeIndex builds in memory and retrieves files for projects."""
        sample_code_path = self.test_path / "sample_code.jsonl"
        records = [
            {"project_id": "proj_1", "path": "project.godot", "content": 'config_version=5\n[application]\nconfig/name="Game 1"\nrun/main_scene="res://main.tscn"'},
            {"project_id": "proj_1", "path": "main.tscn", "content": '[gd_scene load_steps=1 format=3]\n[node name="Main" type="Node2D"]'},
            {"project_id": "proj_2", "path": "player.gd", "content": "extends CharacterBody2D\nfunc _physics_process(delta: float) -> void:\n\tpass"},
        ]
        with open(sample_code_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        index = CodeIndex(sample_code_path)
        index.build_index()

        self.assertIn("proj_1", index)
        self.assertIn("proj_2", index)
        self.assertNotIn("proj_3", index)

        files_p1 = index.get_project_files("proj_1")
        self.assertEqual(len(files_p1), 2)
        paths_p1 = {f["path"] for f in files_p1}
        self.assertEqual(paths_p1, {"project.godot", "main.tscn"})

        files_p2 = index.get_project_files("proj_2")
        self.assertEqual(len(files_p2), 1)
        self.assertEqual(files_p2[0]["path"], "player.gd")

    def test_01b_read_only_real_data_join(self):
        """Read-only integration test: join a real project from structured/ with real code files."""
        if not self.projects_file.exists() or not self.code_file.exists():
            self.skipTest("Real structured/ datasets not available in workspace")

        index = CodeIndex(self.code_file)
        index.build_index()

        # Read first project
        real_project = None
        with open(self.projects_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    p = json.loads(line)
                    if p.get("project_id") in index:
                        real_project = p
                        break

        self.assertIsNotNone(real_project, "Could not find a project present in code index")
        proj_id = real_project["project_id"]
        joined_files = index.get_project_files(proj_id)
        self.assertGreater(len(joined_files), 0, f"Expected real files joined for {proj_id}")
        self.assertTrue(all(f.get("content") is not None for f in joined_files))

    # -------------------------------------------------------------------------
    # 2. Missing and duplicate file paths
    # -------------------------------------------------------------------------
    def test_02_missing_and_duplicate_paths(self):
        """Explicitly handles duplicate file paths, unmatched files, and missing IDs."""
        sample_code_path = self.test_path / "duplicates.jsonl"
        records = [
            {"project_id": "proj_dup", "path": "main.gd", "content": "extends Node\nfunc _ready():\n\tprint('first')"},
            {"project_id": "proj_dup", "path": "main.gd", "content": "extends Node\nfunc _ready():\n\tprint('second duplicate')"},
            {"project_id": "proj_dup", "path": "res://main.gd", "content": "extends Node\nfunc _ready():\n\tprint('third normalized duplicate')"},
            {"project_id": "", "path": "orphan.gd", "content": "extends Node"},
            {"path": "no_project_id.gd", "content": "extends Node"},
        ]
        with open(sample_code_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        index = CodeIndex(sample_code_path)
        index.build_index()

        # Missing project IDs are skipped from index keys
        self.assertIn("proj_dup", index)
        self.assertNotIn("", index)

        files = index.get_project_files("proj_dup")
        # Duplicates (including res:// prefix differences) are cleanly deduplicated to 1 entry
        self.assertEqual(len(files), 1)

        # Ingest adapter organizes them and deduplicates cleanly
        mock_proj = {
            "project_id": "proj_dup",
            "project_name": "DupTest",
            "godot_version": "Godot 4.3",
            "entry_scene": "res://main.tscn",
            "scenes": ["main.tscn"],
            "scripts": ["main.gd"],
            "files": [{"path": "main.gd", "type": "gdscript", "size_bytes": 50}],
        }
        plan, audit = map_structured_project_to_production_logic(mock_proj, project_files=files)
        self.assertIsNotNone(plan)
        # Verify no duplicate files within any individual task and all files are res://
        for t in plan["implementation_tasks"]:
            self.assertEqual(len(t["files"]), len(set(t["files"])), f"Task {t['id']} has duplicate files")
            for f_path in t["files"]:
                self.assertTrue(f_path.startswith("res://"), f"File {f_path} not res://")

    # -------------------------------------------------------------------------
    # 3. Real scene hierarchy extraction
    # -------------------------------------------------------------------------
    def test_03_real_scene_hierarchy_extraction(self):
        """Test hierarchical node tree extraction with proper indentation and root type."""
        tscn_content = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://player.gd" id="1_abc"]

[node name="Player" type="CharacterBody3D"]
script = ExtResource("1_abc")

[node name="CollisionShape3D" type="CollisionShape3D" parent="."]

[node name="MeshInstance3D" type="MeshInstance3D" parent="."]

[node name="CameraArm" type="SpringArm3D" parent="."]

[node name="Camera3D" type="Camera3D" parent="CameraArm"]
"""
        analysis = parse_scene_file(tscn_content)
        self.assertEqual(analysis.root_node_name, "Player")
        self.assertEqual(analysis.root_node_type, "CharacterBody3D")
        self.assertEqual(len(analysis.nodes), 5)

        tree = analysis.hierarchy_tree
        self.assertGreaterEqual(len(tree), 5)
        # Root node must be first and end with (CharacterBody3D)
        self.assertTrue(tree[0].endswith("(CharacterBody3D)"))
        self.assertEqual(tree[0], "Player (CharacterBody3D)")
        # Children must be indented
        self.assertTrue(tree[1].startswith("  CollisionShape3D"))
        # Camera3D is nested under CameraArm -> 4 spaces
        camera_line = next(line for line in tree if "Camera3D" in line)
        self.assertTrue(camera_line.startswith("    Camera3D (Camera3D)"))

    # -------------------------------------------------------------------------
    # 4. Scene-to-script references
    # -------------------------------------------------------------------------
    def test_04_scene_to_script_references(self):
        """Test scene parser extracting attached script references and linking to GDScript."""
        tscn = """[gd_scene load_steps=2 format=3]
[ext_resource type="Script" path="res://scripts/combat_manager.gd" id="1_xyz"]
[node name="CombatManager" type="Node"]
script = ExtResource("1_xyz")
"""
        analysis = parse_scene_file(tscn)
        self.assertEqual(analysis.attached_script, "res://scripts/combat_manager.gd")
        self.assertIn("1_xyz", analysis.ext_resources)
        self.assertEqual(analysis.ext_resources["1_xyz"]["path"], "res://scripts/combat_manager.gd")

    # -------------------------------------------------------------------------
    # 5. Autoload and resource references
    # -------------------------------------------------------------------------
    def test_05_autoload_and_resource_references(self):
        """Test extraction of autoload singletons and external resources."""
        proj_godot = """config_version=5

[application]
config/name="AutoloadDemo"
run/main_scene="res://scenes/world.tscn"

[autoload]
GameState="*res://singletons/game_state.gd"
AudioManager="res://singletons/audio_manager.tscn"

[input]
jump={"deadzone": 0.5, "events": []}
"""
        cfg = parse_project_godot(proj_godot)
        self.assertEqual(cfg.main_scene, "res://scenes/world.tscn")
        self.assertIn("GameState", cfg.autoloads)
        self.assertIn("AudioManager", cfg.autoloads)
        self.assertEqual(cfg.autoloads["GameState"], "res://singletons/game_state.gd")
        self.assertEqual(cfg.autoloads["AudioManager"], "res://singletons/audio_manager.tscn")
        self.assertIn("jump", cfg.input_actions)

    # -------------------------------------------------------------------------
    # 6. Project graph construction and missing dependencies
    # -------------------------------------------------------------------------
    def test_06_project_graph_and_missing_dependencies(self):
        """Test building dependency graph, circularity detection, and missing dependencies."""
        graph = ProjectGraph()
        graph.add_node("res://scenes/main.tscn", "scene", {"type": "Node2D"})
        graph.add_node("res://scripts/main.gd", "script", {"class": "Main"})
        graph.add_node("res://scripts/player.gd", "script", {"class": "Player"})

        graph.add_edge("res://scenes/main.tscn", "res://scripts/main.gd", "attaches_script")
        graph.add_edge("res://scripts/main.gd", "res://scripts/player.gd", "preloads")

        self.assertIn("res://scenes/main.tscn", graph.nodes)
        self.assertEqual(len(graph.nodes), 3)

        # Cycle detection
        self.assertFalse(graph.has_cycles())
        # Add cycle
        graph.add_edge("res://scripts/player.gd", "res://scripts/main.gd", "preloads")
        self.assertTrue(graph.has_cycles())
        cycles = graph.find_circular_dependencies()
        self.assertGreater(len(cycles), 0)

        # Missing external dependencies check
        files_known = {"res://scenes/main.tscn", "res://scripts/main.gd", "res://scripts/player.gd"}
        scene_deps = [{"scene": "res://scenes/main.tscn", "dependencies": ["res://scripts/player.gd", "res://scenes/missing.tscn"]}]
        autoloads = {"MissingGlobal": "res://scripts/missing_global.gd"}
        dep_rep = analyze_dependencies(files_known, scene_deps, autoloads)
        self.assertFalse(dep_rep.is_valid)
        self.assertGreater(len(dep_rep.unresolved_references), 0)

    # -------------------------------------------------------------------------
    # 7. Canonical production-logic schema compatibility
    # -------------------------------------------------------------------------
    def test_07_canonical_production_logic_compatibility(self):
        """Test full plan generation and verification against canonical rules."""
        mock_project = {
            "project_id": "project:canonical_test",
            "project_name": "SpaceShooter",
            "godot_version": "Godot 4.2",
            "entry_scene": "res://scenes/main.tscn",
            "scenes": ["res://scenes/main.tscn"],
            "scripts": ["res://scripts/player.gd", "res://scripts/enemy.gd"],
            "summary_text": "A classic 2D space shooter demo with player and enemies.",
        }
        files = [
            {
                "path": "project.godot",
                "content": 'config_version=5\n[application]\nconfig/name="SpaceShooter"\nrun/main_scene="res://scenes/main.tscn"\n[autoload]\nScoreManager="*res://scripts/score_manager.gd"\n',
            },
            {
                "path": "scenes/main.tscn",
                "content": '[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://scripts/player.gd" id="1_p"]\n[node name="Main" type="Node2D"]\n[node name="Player" type="CharacterBody2D" parent="."]\nscript = ExtResource("1_p")\n',
            },
            {
                "path": "scripts/player.gd",
                "content": 'extends CharacterBody2D\nclass_name Player\n@export var speed: float = 300.0\nsignal health_changed(new_hp: int)\nfunc take_damage(amount: int) -> void:\n\thealth_changed.emit(10)\nfunc _physics_process(delta: float) -> void:\n\tpass\n',
            },
            {
                "path": "scripts/enemy.gd",
                "content": 'extends Area2D\nclass_name Enemy\nfunc spawn() -> void:\n\tpass\n',
            },
            {
                "path": "scripts/score_manager.gd",
                "content": 'extends Node\nvar score: int = 0\nfunc add_score(pts: int) -> void:\n\tscore += pts\n',
            },
        ]

        plan, audit = map_structured_project_to_production_logic(mock_project, project_files=files)
        self.assertIsNotNone(plan)

        # 1. JSON Schema validation
        schema_valid, schema_errs = validate_against_schema("production_logic", plan)
        self.assertTrue(schema_valid, f"Schema validation failed: {schema_errs}")

        # 2. Canonical validation (exact rules from dev/validate.py)
        can_valid, can_errs = check_canonical_plan(plan)
        self.assertTrue(can_valid, f"Canonical validation failed: {can_errs}")

    # -------------------------------------------------------------------------
    # 8. Honest handling of missing evidence
    # -------------------------------------------------------------------------
    def test_08_honest_handling_of_missing_evidence(self):
        """Limitations and unverified runtime states are honestly marked."""
        mock_project = {
            "project_id": "project:untested",
            "project_name": "UntestedDemo",
            "godot_version": "Godot 4.2",
            "scenes": ["res://main.tscn"],
            "scripts": ["res://main.gd"],
        }
        files = [
            {"path": "main.tscn", "content": '[gd_scene format=3]\n[node name="Main" type="Node2D"]\n'},
            {"path": "main.gd", "content": 'extends Node2D\nfunc start() -> void:\n\tpass\n'},
        ]
        plan, _ = map_structured_project_to_production_logic(mock_project, project_files=files)
        self.assertIsNotNone(plan)

        # Honest execution state
        self.assertEqual(plan["execution_state"], "plan_only_no_actions_executed")

        # Honest verification plan status
        for v in plan["verification_plan"]:
            self.assertEqual(v["status"], "not_run", "Extracted plans must not claim tests passed")

        # Honest failure analysis status
        self.assertIsInstance(plan["failure_analysis"], list)
        self.assertGreater(len(plan["failure_analysis"]), 0)
        for fa in plan["failure_analysis"]:
            self.assertEqual(fa["repair_status"], "proposed")
            self.assertEqual(fa["cause_status"], "hypothesis_unconfirmed")

    # -------------------------------------------------------------------------
    # 9. Debugging records with unverified fixes
    # -------------------------------------------------------------------------
    def test_09_debugging_records_with_unverified_fixes(self):
        """Debugging repairs must never be labeled as verified unless runtime evidence exists."""
        raw_debug = {
            "issue_id": "issue-42",
            "problem": "Player passes through walls at high speeds",
            "solution": "Enable continuous collision detection or reduce velocity step",
            "patch": "",
            "discussion": "We noticed this happens in _physics_process when delta is large.\nProposed fix is CCD.",
            "context": "CharacterBody2D script with move_and_slide()",
            "godot_version": "Godot 4.2",
            "repository": "godotengine/demo",
        }
        debug_rec, audit = map_structured_debugging_to_repair(raw_debug)
        self.assertIsNotNone(debug_rec)
        self.assertFalse(debug_rec["is_verified"])
        self.assertFalse(debug_rec["runtime_tested"])
        self.assertEqual(debug_rec["verification_result"], "unverified_discussion_only")
        self.assertEqual(debug_rec["fix_type"], "conceptual_solution")

        # Schema validation
        is_valid, errs = validate_against_schema("debugging_repair", debug_rec)
        self.assertTrue(is_valid, f"Debugging schema errors: {errs}")

    # -------------------------------------------------------------------------
    # 10. Project-level dataset splitting
    # -------------------------------------------------------------------------
    def test_10_project_level_dataset_splitting(self):
        """Verifies no project leaks across train/val/test splits and seeding is deterministic."""
        records = [
            {"project_id": "repoA", "content": "file1 in A"},
            {"project_id": "repoA", "content": "file2 in A"},
            {"project_id": "repoB", "content": "file1 in B"},
            {"project_id": "repoC", "content": "file1 in C"},
            {"project_id": "repoD", "content": "file1 in D"},
            {"project_id": "repoE", "content": "file1 in E"},
        ]

        splits1 = split_dataset_by_project(records, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2, seed=42)
        splits2 = split_dataset_by_project(records, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2, seed=42)

        # Determinism check
        self.assertEqual(splits1.split_counts, splits2.split_counts)
        self.assertEqual(splits1.project_split_map, splits2.project_split_map)

        # Leakage check: repoA records must all be in the same split!
        repoA_splits = {splits1.project_split_map["repoA"]}
        self.assertEqual(len(repoA_splits), 1)

        train_repos = {r["project_id"] for r in splits1.train}
        val_repos = {r["project_id"] for r in splits1.val}
        test_repos = {r["project_id"] for r in splits1.test}

        self.assertTrue(train_repos.isdisjoint(val_repos), "Train and Val share project IDs!")
        self.assertTrue(train_repos.isdisjoint(test_repos), "Train and Test share project IDs!")
        self.assertTrue(val_repos.isdisjoint(test_repos), "Val and Test share project IDs!")

    # -------------------------------------------------------------------------
    # 11. Exporting real records rather than fixture fallbacks
    # -------------------------------------------------------------------------
    def test_11_export_real_records_no_fixture_fallback(self):
        """Exporter must use real ingested/cleaned records when present."""
        ingested_dir = self.test_path / "ingested"
        ingested_dir.mkdir(parents=True)
        export_out = self.test_path / "export_out"

        real_plan = {
            "project_id": "proj_real_1",
            "plan": {
                "project_summary": "Real Project One",
                "assumptions": ["Standard 2D physics"],
                "requirements": {"functional": ["Move player"], "nonfunctional": ["60 fps"]},
                "gameplay_loop": ["Spawn", "Move", "Clear"],
                "architecture": {"entry_scene": "res://main.tscn", "folders": ["res://"], "autoloads": [], "communication": [], "physics_layers": [], "engine_apis_used": [], "api_note": ""},
                "scenes": [{"path": "res://main.tscn", "name": "Main", "root_type": "Node2D", "hierarchy": ["Main (Node2D)"], "attached_script": "res://main.gd", "instanced_scenes": [], "dependencies": []}],
                "systems": [{"name": "Main", "script_path": "res://main.gd", "extends": "Node2D", "role": "Controller", "public_methods_project_defined": ["init()"], "signals_declared": [], "dependencies": []}],
                "dependencies": {"external_assets": [], "internal_scenes": ["res://main.tscn"], "internal_scripts": ["res://main.gd"], "autoload_singletons": []},
                "implementation_tasks": [{"id": "task_0", "title": "Setup Main", "description": "Setup", "files": ["res://main.tscn", "res://main.gd"], "prerequisites": [], "status": "proposed"}],
                "acceptance_criteria": [{"id": "ac_0", "task_id": "task_0", "description": "Criteria", "verification": "Manual inspect"}],
                "risks": [{"risk": "None", "mitigation": "None"}],
                "verification_plan": [{"step": "Inspect", "type": "manual_inspection", "target": "main.tscn", "status": "not_run"}],
                "failure_analysis": {"potential_failure": "None", "root_cause_hypothesis": "None", "repair_strategy": "None", "repair_status": "proposed", "cause_status": "hypothesis_unconfirmed"},
                "execution_state": "plan_only_no_actions_executed",
            }
        }
        with open(ingested_dir / "dataset_a_projects.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps(real_plan) + "\n")

        cfg = AppConfig(
            sources=SourcesConfig(),
            pipeline=PipelineConfig(base_dir=self.test_path, data_dir=self.test_path, training_dir=export_out, cleaned_dir=self.test_path / "cleaned"),
            cleaning=CleaningRules(),
            validation=ValidationRules(),
        )

        args = argparse.Namespace(output_dir=export_out, use_fixtures=False, include_trajectories=False)
        ret = cmd_export(cfg, args)
        self.assertEqual(ret, 0)

        # Check exported files
        self.assertTrue((export_out / "dataset_a_production_logic_train.jsonl").exists() or
                        (export_out / "dataset_a_production_logic_val.jsonl").exists() or
                        (export_out / "dataset_a_production_logic_test.jsonl").exists())
        # Fixture file should NOT exist
        self.assertFalse((export_out / "train_fixtures_sharegpt.jsonl").exists())

    # -------------------------------------------------------------------------
    # 12. Empty input and all-records-rejected behavior
    # -------------------------------------------------------------------------
    def test_12_empty_input_rejected_behavior(self):
        """Exporter must fail clearly with exit code 1 if no real records exist and --use-fixtures not set."""
        empty_data_dir = self.test_path / "empty_data"
        empty_data_dir.mkdir(parents=True)
        export_out = self.test_path / "export_fail"

        cfg = AppConfig(
            sources=SourcesConfig(),
            pipeline=PipelineConfig(base_dir=self.test_path, data_dir=empty_data_dir, training_dir=export_out, cleaned_dir=empty_data_dir / "cleaned"),
            cleaning=CleaningRules(),
            validation=ValidationRules(),
        )

        args = argparse.Namespace(output_dir=export_out, use_fixtures=False, include_trajectories=False)
        ret = cmd_export(cfg, args)
        self.assertEqual(ret, 1, "cmd_export should return code 1 when no records exist and use_fixtures=False")

    # -------------------------------------------------------------------------
    # 13. Idempotent execution and safe output handling
    # -------------------------------------------------------------------------
    def test_13_idempotent_execution_and_safe_output_handling(self):
        """Exporter must not overwrite existing output files by default; creates versioned directory."""
        data_dir = self.test_path / "safe_data"
        ingested = data_dir / "ingested"
        ingested.mkdir(parents=True)
        default_training = self.test_path / "training"
        default_training.mkdir(parents=True)

        # Create a pre-existing export file in default_training
        existing_marker = default_training / "existing_dataset.jsonl"
        with open(existing_marker, "w", encoding="utf-8") as f:
            f.write('{"test": true}\n')

        # Add mock real record
        with open(ingested / "dataset_a_projects.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({"project_id": "p1", "plan": {"project_summary": "P1"}}) + "\n")

        cfg = AppConfig(
            sources=SourcesConfig(),
            pipeline=PipelineConfig(base_dir=self.test_path, data_dir=data_dir, training_dir=default_training, cleaned_dir=data_dir / "cleaned"),
            cleaning=CleaningRules(),
            validation=ValidationRules(),
        )

        # Call export without explicit --output-dir
        args = argparse.Namespace(output_dir=None, use_fixtures=False, include_trajectories=False)
        ret = cmd_export(cfg, args)
        self.assertEqual(ret, 0)

        # Check that existing_marker was NOT deleted or overwritten
        self.assertTrue(existing_marker.exists())

        # Check that a versioned run directory was created
        versioned_dirs = [p for p in default_training.glob("run_*") if p.is_dir()]
        self.assertEqual(len(versioned_dirs), 1, "Expected a versioned run directory to be created")


if __name__ == "__main__":
    unittest.main()
