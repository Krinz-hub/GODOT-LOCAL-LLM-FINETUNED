import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import unittest

from logic_pipeline.processing.deduplicate import Deduplicator
from logic_pipeline.provenance import ProvenanceMetadata


class TestDeduplication(unittest.TestCase):
    def test_exact_deduplication(self):
        deduper = Deduplicator(near_duplicate_threshold=0.85)
        records = [
            {
                "record_id": "rec-1",
                "normalized_content": "extends CharacterBody2D\nfunc _physics_process(delta):\n\tpass\n",
                "provenance": ProvenanceMetadata(source_id="s1", source_type="local", source_url="url1").to_dict(),
            },
            {
                "record_id": "rec-2",
                "normalized_content": "extends CharacterBody2D\nfunc _physics_process(delta):\n\tpass\n",
                "provenance": ProvenanceMetadata(source_id="s2", source_type="github", source_url="url2").to_dict(),
            },
        ]
        res = deduper.process_records(records)
        self.assertEqual(len(res.unique_records), 1)
        self.assertEqual(res.exact_duplicates_count, 1)
        # Provenance merged
        merged_prov = res.unique_records[0]["provenance"]
        self.assertEqual(len(merged_prov["secondary_sources"]), 1)
        self.assertEqual(merged_prov["secondary_sources"][0]["source_id"], "s2")

    def test_near_deduplication(self):
        content1 = (
            "extends CharacterBody2D\n"
            "@export var speed: float = 300.0\n"
            "@export var jump_velocity: float = -400.0\n"
            "func _physics_process(delta: float) -> void:\n"
            "    velocity += get_gravity() * delta\n"
            "    move_and_slide()\n"
        )
        content2 = (
            "extends CharacterBody2D\n"
            "@export var speed: float = 350.0\n"
            "@export var jump_velocity: float = -400.0\n"
            "func _physics_process(delta: float) -> void:\n"
            "    velocity += get_gravity() * delta\n"
            "    move_and_slide()\n"
        )

        records = [
            {"record_id": "r1", "normalized_content": content1},
            {"record_id": "r2", "normalized_content": content2},
        ]
        # When flag_only=False (merge mode)
        deduper_merge = Deduplicator(near_duplicate_threshold=0.80, flag_only=False)
        res_merge = deduper_merge.process_records(records)
        self.assertEqual(len(res_merge.unique_records), 1)
        self.assertEqual(res_merge.near_duplicates_count, 1)

        # When flag_only=True (safe mode, preserves distinct implementations)
        deduper_safe = Deduplicator(near_duplicate_threshold=0.80, flag_only=True)
        res_safe = deduper_safe.process_records(records)
        self.assertEqual(len(res_safe.unique_records), 2)
        self.assertEqual(res_safe.near_duplicates_count, 1)
        self.assertEqual(res_safe.unique_records[1]["near_duplicate_of"], "r1")

    def test_distinct_content_preserved(self):
        deduper = Deduplicator(near_duplicate_threshold=0.85)
        records = [
            {"record_id": "r1", "normalized_content": "extends Node\nfunc _ready():\n    print('Hello World')\n"},
            {"record_id": "r2", "normalized_content": "extends Resource\nclass_name InventoryItem\n@export var id: int = 1\n"},
        ]
        res = deduper.process_records(records)
        self.assertEqual(len(res.unique_records), 2)
        self.assertEqual(res.exact_duplicates_count, 0)
        self.assertEqual(res.near_duplicates_count, 0)


if __name__ == "__main__":
    unittest.main()
