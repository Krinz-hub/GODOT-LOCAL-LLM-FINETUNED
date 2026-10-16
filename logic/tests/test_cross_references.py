import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import unittest

from logic_pipeline.validation.cross_references import validate_cross_references
from logic_pipeline.analysis.dependency_analysis import analyze_task_prerequisites
from logic_pipeline.config import find_logic_root


class TestCrossReferences(unittest.TestCase):
    def setUp(self):
        sample_file = find_logic_root() / "tests" / "fixtures" / "sample_production_logic.jsonl"
        with open(sample_file, "r", encoding="utf-8") as f:
            rec = json.loads(f.readline())
        self.valid_plan = json.loads(rec["messages"][2]["content"])

    def test_valid_plan_cross_references(self):
        rep = validate_cross_references(self.valid_plan)
        self.assertTrue(rep.is_valid)
        self.assertEqual(len(rep.errors), 0)

    def test_missing_task_prerequisite_error(self):
        plan = dict(self.valid_plan)
        # Introduce a non-existent prerequisite 'T99'
        plan["implementation_tasks"] = [
            {
                "id": "T1",
                "description": "Task 1",
                "files": ["res://player.gd"],
                "prerequisites": ["T99"],  # Non-existent
                "expected_output": "out",
                "completion_conditions": "done",
                "verification": "test",
                "recovery": "fix",
                "status": "proposed",
            }
        ]
        rep = validate_cross_references(plan)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any("T99" in err for err in rep.errors))

    def test_task_prerequisite_circularity(self):
        # T1 -> T2 -> T1 cycle
        tasks = [
            {"id": "T1", "prerequisites": ["T2"]},
            {"id": "T2", "prerequisites": ["T1"]},
        ]
        rep = analyze_task_prerequisites(tasks)
        self.assertFalse(rep.is_valid)
        self.assertTrue(len(rep.circular_dependencies) > 0)

    def test_acceptance_criteria_task_mismatch(self):
        plan = dict(self.valid_plan)
        plan["acceptance_criteria"] = [
            {"id": "AC1", "criterion": "Passes", "verified_by_task": "T_UNKNOWN", "status": "not_run"}
        ]
        rep = validate_cross_references(plan)
        self.assertTrue(any("T_UNKNOWN" in w for w in rep.warnings))


if __name__ == "__main__":
    unittest.main()
