"""Tests for structured Godot dataset ingestion adapter and schema mappers."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from logic_pipeline.config import find_logic_root
from logic_pipeline.extractors.structured_mappers import (
    map_structured_project_to_production_logic,
    map_structured_debugging_to_repair,
    map_structured_agent_task_to_trajectory,
)
from logic_pipeline.processing.export_training import (
    export_dataset_a_to_sharegpt,
    export_dataset_b_to_sharegpt,
    export_dataset_c_to_sharegpt,
)
from logic_pipeline.sources.structured_ingest import StructuredIngestionAdapter
from logic_pipeline.validation.cross_references import validate_cross_references
from logic_pipeline.validation.schema import validate_against_schema


class TestStructuredIngestionAdapter(unittest.TestCase):
    def setUp(self):
        self.logic_root = find_logic_root()
        self.workspace_root = self.logic_root.parent
        self.adapter = StructuredIngestionAdapter(
            workspace_root=self.workspace_root,
            logic_root=self.logic_root,
        )

    def test_check_inputs_available(self):
        """Verifies that structured input datasets are available and read-only with valid SHA-256."""
        status = self.adapter.check_inputs_available()
        self.assertIn("projects", status)
        self.assertIn("debugging", status)
        self.assertIn("agent_tasks", status)

        self.assertTrue(status["projects"]["exists"])
        self.assertTrue(status["debugging"]["exists"])
        self.assertTrue(status["agent_tasks"]["exists"])

        # Hashes match verified SHA-256 signatures
        self.assertEqual(
            status["projects"]["sha256"],
            "f45a06efa10b36fcb1ef1e2075db336cd0c2cfcc592f43bcf22977bf60d8601c",
        )
        self.assertEqual(
            status["debugging"]["sha256"],
            "89388da4804feeb0f2f958f437d6c4012b2dde2d91bf2858db6fde49eac22a07",
        )
        self.assertEqual(
            status["agent_tasks"]["sha256"],
            "d6887298e4ba7118519a6837fb15a038ce7ea657746548f75108f2d15f0e0a59",
        )

    def test_map_structured_project_conforms_to_schema(self):
        """Ensures Dataset A mapper creates plans that fully validate against production_logic.schema.json."""
        sample_project_record = {
            "record_type": "godot_project",
            "project_id": "project:2Retr0/GodotOceanWaves",
            "project_name": "OceanWaves",
            "project_path": "2Retr0/GodotOceanWaves",
            "repository": "2Retr0/GodotOceanWaves",
            "godot_version": "Godot 4.3",
            "version_confidence": 0.98,
            "version_source": "project.godot",
            "entry_scene": "res://main.tscn",
            "project_file": "project.godot",
            "files": [
                {"path": "main.tscn", "type": "godot_scene", "size_bytes": 5316},
                {"path": "main.gd", "type": "gdscript", "size_bytes": 9064},
                {"path": "water.gd", "type": "gdscript", "size_bytes": 5110},
            ],
            "scripts": ["main.gd", "water.gd"],
            "scenes": ["main.tscn"],
            "resources": [],
            "shaders": [],
            "important_systems": ["water_generator"],
            "summary_text": "An interactive 3D ocean water simulation demo in Godot 4.3.",
            "source": "github",
            "source_url": "https://github.com/2Retr0/GodotOceanWaves",
            "license": "MIT",
        }

        plan, audit = map_structured_project_to_production_logic(sample_project_record)
        self.assertIsNotNone(plan)
        self.assertEqual(audit["status"], "mapped")
        self.assertEqual(audit["evidence_level"], "sufficient_evidence")

        # 1. JSON Schema validation
        is_valid, errors = validate_against_schema("production_logic", plan)
        self.assertTrue(is_valid, f"Plan failed production_logic schema validation: {errors}")

        # 2. Cross-reference validation
        xref_rep = validate_cross_references(plan)
        self.assertTrue(xref_rep.is_valid, f"Cross-reference issues: {xref_rep.errors}")

        # 3. Execution state check
        self.assertEqual(plan["execution_state"], "plan_only_no_actions_executed")

    def test_dataset_a_quarantine_reasons(self):
        """Ensures incompatible engine versions and empty records are properly quarantined."""
        # Godot 3 record
        g3_rec = {
            "project_id": "proj:legacy",
            "godot_version": "Godot 3.2.3",
            "files": [{"path": "main.tscn", "type": "godot_scene", "size_bytes": 100}],
            "scenes": ["main.tscn"],
            "scripts": [],
        }
        plan_g3, audit_g3 = map_structured_project_to_production_logic(g3_rec)
        self.assertIsNone(plan_g3)
        self.assertEqual(audit_g3["status"], "quarantined")
        self.assertIn("Godot 4.x", audit_g3["quarantine_reason"])

        # Empty record
        empty_rec = {"project_id": "proj:empty", "godot_version": "Godot 4.2"}
        plan_emp, audit_emp = map_structured_project_to_production_logic(empty_rec)
        self.assertIsNone(plan_emp)
        self.assertEqual(audit_emp["status"], "quarantined")

    def test_map_structured_debugging_conforms_to_schema(self):
        """Ensures Dataset B mapper creates records that validate against debugging_repair.schema.json."""
        sample_debugging_record = {
            "record_type": "debugging",
            "issue_id": "github-issue:godotengine/godot:45492",
            "instruction": "Diagnose and resolve Godot issue: Sprite pivot point scrolls with texture offset",
            "problem": "Sprite pivot point scrolls along with the texture offset in Godot 4.",
            "error": None,
            "context": "Node2D -> Sprite2D with offset",
            "discussion": "From my tests the pivot doesn't change, the offset happens because of distance.",
            "solution": "Adjust the region rect position from the center of the texture.",
            "patch": None,
            "related_code": [{"code": "sprite.offset = Vector2(10, 10)"}],
            "godot_version": "Godot 4.x",
            "license": "MIT",
        }

        rec, audit = map_structured_debugging_to_repair(sample_debugging_record)
        self.assertIsNotNone(rec)
        self.assertEqual(audit["status"], "mapped")
        self.assertTrue(audit["requires_human_review"])  # Because patch is conceptual

        # Schema validation
        is_valid, errors = validate_against_schema("debugging_repair", rec)
        self.assertTrue(is_valid, f"Debugging record failed schema validation: {errors}")
        self.assertEqual(rec["execution_state"], "reconstructed_from_issue_discussion")

    def test_map_structured_agent_task_conforms_to_schema(self):
        """Ensures Dataset C mapper creates records that validate against agent_trajectory.schema.json."""
        sample_task_record = {
            "record_type": "agent_task",
            "task_id": "github-pr:godotengine/godot-demo-projects:1351",
            "instruction": "Implement change: Fix main scene in custom_logging demo",
            "task": "Fix main scene in custom_logging demo",
            "context": "Use main.tscn as the main scene instead of custom_logger_ui.tscn",
            "patch": "diff --git a/project.godot b/project.godot\n--- a/project.godot\n+++ b/project.godot\n@@ -1,3 +1,3 @@\n-run/main_scene=\"ui.tscn\"\n+run/main_scene=\"main.tscn\"\n",
            "files_changed": ["misc/custom_logging/project.godot"],
            "reasoning": "Merged PR in demo projects fixing main scene pointer.",
            "tests": ["Project builds and passes test suite"],
            "synthetic": False,
            "godot_version": "Godot 4.x",
            "repository": "godotengine/godot-demo-projects",
            "pr_number": 1351,
            "license": "MIT",
        }

        traj, audit = map_structured_agent_task_to_trajectory(sample_task_record)
        self.assertIsNotNone(traj)
        self.assertEqual(audit["status"], "mapped")
        self.assertFalse(traj["is_synthetic"])

        # Schema validation
        is_valid, errors = validate_against_schema("agent_trajectory", traj)
        self.assertTrue(is_valid, f"Trajectory failed agent_trajectory schema validation: {errors}")
        self.assertEqual(len(traj["steps"]), 4)
        self.assertEqual(traj["final_verification_result"], "passed")

    def test_dataset_separation_export(self):
        """Verifies that Datasets A, B, and C produce separate, non-overlapping ShareGPT formats."""
        # Dataset A item
        item_a = {
            "project_id": "proj:test",
            "plan": {
                "project_summary": "Test A Project",
                "assumptions": [],
                "requirements": {"functional": [], "nonfunctional": []},
                "gameplay_loop": [],
                "architecture": {"entry_scene": "res://main.tscn", "folders": [], "autoloads": {}, "engine_apis_used": []},
                "scenes": [],
                "systems": [],
                "dependencies": [],
                "implementation_tasks": [],
                "acceptance_criteria": [],
                "risks": [],
                "verification_plan": [],
                "failure_analysis": [],
                "execution_state": "plan_only_no_actions_executed",
            },
        }
        sg_a = export_dataset_a_to_sharegpt([item_a])
        self.assertEqual(len(sg_a), 1)
        self.assertEqual(sg_a[0]["dataset_type"], "dataset_a_production_logic")

        # Dataset B item
        item_b = {
            "issue_id": "issue:1",
            "record": {
                "problem": "Error loading node",
                "context": "main.gd",
                "root_cause": "Null reference",
                "proposed_fix": "Add guard",
                "fix_type": "conceptual_solution",
                "verification_result": "passed",
                "limitations": "none",
                "execution_state": "reconstructed",
            },
        }
        sg_b = export_dataset_b_to_sharegpt([item_b])
        self.assertEqual(len(sg_b), 1)
        self.assertEqual(sg_b[0]["dataset_type"], "dataset_b_debugging")

        # Dataset C item
        item_c = {
            "trajectory_id": "traj:1",
            "record": {
                "trajectory_id": "traj:1",
                "user_request": "Fix button state",
                "environment": {"godot_version": "4.x", "os": "linux"},
                "is_synthetic": False,
                "steps": [
                    {
                        "step_index": 1,
                        "decision": "Inspect files",
                        "tool_call": "inspect",
                        "tool_input": {},
                        "tool_output": None,
                        "observed_result": "inspected",
                    }
                ],
                "final_verification_result": "passed",
            },
        }
        sg_c = export_dataset_c_to_sharegpt([item_c])
        self.assertEqual(len(sg_c), 1)
        self.assertEqual(sg_c[0]["dataset_type"], "dataset_c_trajectories")

        # Confirm distinct tags
        self.assertNotEqual(sg_a[0]["dataset_type"], sg_b[0]["dataset_type"])
        self.assertNotEqual(sg_b[0]["dataset_type"], sg_c[0]["dataset_type"])

    def test_ingest_sample_dry_run(self):
        """Verifies dry-run ingestion executes and computes statistics without disk mutation."""
        summary_a = self.adapter.ingest_dataset_a(sample_size=10, dry_run=True)
        self.assertEqual(summary_a.records_examined, 10)
        self.assertGreater(summary_a.records_mapped + summary_a.records_quarantined, 0)

        summary_b = self.adapter.ingest_dataset_b(sample_size=5, dry_run=True)
        self.assertEqual(summary_b.records_examined, 5)

        summary_c = self.adapter.ingest_dataset_c(sample_size=10, dry_run=True)
        self.assertEqual(summary_c.records_examined, 10)


if __name__ == "__main__":
    unittest.main()
