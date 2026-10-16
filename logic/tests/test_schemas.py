import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import unittest

from logic_pipeline.validation.schema import validate_against_schema
from logic_pipeline.config import find_logic_root


class TestSchemas(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = find_logic_root() / "tests" / "fixtures"

    def test_production_logic_schema(self):
        sample_file = self.fixtures_dir / "sample_production_logic.jsonl"
        with open(sample_file, "r", encoding="utf-8") as f:
            rec = json.loads(f.readline())
        plan = json.loads(rec["messages"][2]["content"])

        is_valid, errors = validate_against_schema("production_logic", plan)
        self.assertTrue(is_valid, f"Validation failed with: {errors}")

    def test_production_logic_schema_rejection(self):
        # Missing required 'architecture' and 'scenes'
        bad_plan = {
            "project_summary": "Bad plan",
            "assumptions": [],
            "requirements": {},
            "gameplay_loop": [],
        }
        is_valid, errors = validate_against_schema("production_logic", bad_plan)
        self.assertFalse(is_valid)
        self.assertTrue(len(errors) > 0)

    def test_source_record_schema(self):
        record = {
            "source_id": "test:src:1",
            "source_type": "local",
            "source_url": "file:///path/to/project",
            "retrieval_timestamp": "2026-10-15T12:00:00Z",
            "license": "MIT",
            "content_hash": "abcdef1234567890",
        }
        is_valid, errors = validate_against_schema("source_record", record)
        self.assertTrue(is_valid, f"Validation failed: {errors}")

    def test_agent_trajectory_schema(self):
        traj = {
            "trajectory_id": "traj-001",
            "user_request": "Add coin collection sound",
            "is_synthetic": True,
            "steps": [
                {
                    "step_index": 1,
                    "decision": "Inspect AudioStreamPlayer2D node in main.tscn",
                    "tool_call": "read_scene",
                    "tool_input": {"path": "res://main.tscn"},
                    "tool_output": "[node name='Audio' type='AudioStreamPlayer2D']",
                    "observed_result": "Node found",
                }
            ],
            "final_verification_result": "passed",
        }
        is_valid, errors = validate_against_schema("agent_trajectory", traj)
        self.assertTrue(is_valid, f"Validation failed: {errors}")


if __name__ == "__main__":
    unittest.main()
