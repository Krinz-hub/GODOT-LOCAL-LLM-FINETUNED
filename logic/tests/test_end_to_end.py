import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import tempfile
import unittest

from logic_pipeline.config import AppConfig, SourcesConfig, PipelineConfig, CleaningRules, ValidationRules, find_logic_root
from logic_pipeline.sources.local_projects import LocalProjectsSource
from logic_pipeline.processing.normalize import normalize_record
from logic_pipeline.processing.clean import clean_content
from logic_pipeline.processing.deduplicate import Deduplicator
from logic_pipeline.processing.split_dataset import split_dataset_by_project
from logic_pipeline.processing.export_training import (
    export_scene_script_to_sharegpt,
    export_production_logic_to_sharegpt,
    export_to_sharegpt,
)
from logic_pipeline.validation.schema import validate_against_schema
from logic_pipeline.validation.cross_references import validate_cross_references
from logic_pipeline.reporting.dataset_stats import generate_dataset_statistics


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.logic_root = find_logic_root()
        self.fixture_proj = self.logic_root / "tests" / "fixtures" / "sample_project"
        self.fixture_logic = self.logic_root / "tests" / "fixtures" / "sample_production_logic.jsonl"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_pipeline_end_to_end(self):
        # 1. Collection (Local Source)
        src = LocalProjectsSource(project_paths=[str(self.fixture_proj)])
        discovered_items = src.collect(dry_run=False)
        self.assertGreaterEqual(len(discovered_items), 5)

        # 2. Normalization
        normalized_records = []
        for item in discovered_items:
            rec, err = normalize_record(item.to_dict())
            self.assertIsNone(err)
            self.assertIsNotNone(rec)
            normalized_records.append(rec)
        self.assertEqual(len(normalized_records), len(discovered_items))

        # 3. Cleaning
        cleaned_records = []
        quarantined_records = []
        rules = CleaningRules()
        for rec in normalized_records:
            res = clean_content(
                rec.get("normalized_content", ""),
                rules=rules,
                file_path=rec.get("file_path", ""),
            )
            if res.is_clean:
                rec["cleaned_content"] = res.cleaned_content
                cleaned_records.append(rec)
            else:
                quarantined_records.append(rec)
        self.assertGreaterEqual(len(cleaned_records), 3)

        # 4. Deduplication
        deduper = Deduplicator(near_duplicate_threshold=0.85)
        dedup_result = deduper.process_records(cleaned_records)
        self.assertGreaterEqual(len(dedup_result.unique_records), 3)

        # 5. Schema Validation & Cross-References
        with open(self.fixture_logic, "r", encoding="utf-8") as f:
            plan_line = json.loads(f.readline())
        plan = json.loads(plan_line["messages"][2]["content"])

        is_valid, errors = validate_against_schema("production_logic", plan)
        self.assertTrue(is_valid, f"Schema validation failed: {errors}")

        xref = validate_cross_references(plan)
        self.assertTrue(xref.is_valid, f"Cross references failed: {xref.errors}")

        # 6. Formatting & Export
        export_records = []
        # Add formatted plan
        export_records.append(export_production_logic_to_sharegpt(plan))

        # Add script records
        for rec in dedup_result.unique_records:
            if rec.get("file_path", "").endswith(".gd"):
                formatted = export_scene_script_to_sharegpt(
                    filename=Path(rec["file_path"]).name,
                    scene_tree_summary="Root (Node)",
                    gdscript_code=rec["cleaned_content"],
                )
                formatted["repository"] = "sample_project"
                export_records.append(formatted)

        splits = split_dataset_by_project(export_records, train_ratio=0.8, val_ratio=0.1, test_ratio=0.1)
        self.assertGreaterEqual(len(splits.train) + len(splits.val) + len(splits.test), 1)

        # Export file verification
        train_out = self.tmp_path / "train.jsonl"
        count = export_to_sharegpt(splits.train or export_records, train_out)
        self.assertGreaterEqual(count, 1)
        self.assertTrue(train_out.exists())

        # Verify output message structure matches Qwen2.5-Coder expected ShareGPT
        with open(train_out, "r", encoding="utf-8") as f:
            first_line = json.loads(f.readline())
            self.assertIn("messages", first_line)
            roles = [m["role"] for m in first_line["messages"]]
            self.assertEqual(roles, ["system", "user", "assistant"])

        # 7. Statistics
        stats = generate_dataset_statistics(
            raw_count=len(discovered_items),
            normalized_count=len(normalized_records),
            cleaned_count=len(cleaned_records),
            quarantined_count=len(quarantined_records),
        )
        self.assertEqual(stats["stages"]["raw_records"], len(discovered_items))


if __name__ == "__main__":
    unittest.main()
