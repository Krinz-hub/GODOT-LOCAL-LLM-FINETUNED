import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import unittest

from logic_pipeline.processing.clean import clean_content, scrub_sensitive_data
from logic_pipeline.config import CleaningRules


class TestCleaning(unittest.TestCase):
    def setUp(self):
        self.rules = CleaningRules()

    def test_empty_content_quarantine(self):
        res = clean_content("", rules=self.rules)
        self.assertFalse(res.is_clean)
        self.assertEqual(res.quarantine_reason, "EMPTY_CONTENT")

    def test_short_script_quarantine(self):
        short_code = "extends Node\npass\n"
        res = clean_content(short_code, rules=self.rules, file_path="test.gd")
        self.assertFalse(res.is_clean)
        self.assertEqual(res.quarantine_reason, "SCRIPT_TOO_SHORT")

    def test_email_scrubbing(self):
        text = "# Author: developer.godot@example.com\nclass_name Test"
        scrubbed = scrub_sensitive_data(text, redact_emails=True, redact_paths=False)
        self.assertIn("<REDACTED_EMAIL>", scrubbed)
        self.assertNotIn("developer.godot@example.com", scrubbed)

    def test_local_path_scrubbing_with_protocol_preservation(self):
        text = (
            'var local_cache = "/home/piet/Documents/project/cache.dat"\n'
            'var win_path = "C:\\\\Users\\\\developer\\\\Documents\\\\file.txt"\n'
            'var godot_scene = preload("res://scenes/main.tscn")\n'
            'var user_save = "user://saves/slot1.save"\n'
            'var root_node = get_node("/root/GameManager")\n'
        )
        scrubbed = scrub_sensitive_data(text, redact_emails=False, redact_paths=True)
        self.assertIn("<REDACTED_LOCAL_PATH>", scrubbed)
        self.assertNotIn("/home/piet", scrubbed)
        # Verify Godot protocols are preserved!
        self.assertIn("res://scenes/main.tscn", scrubbed)
        self.assertIn("user://saves/slot1.save", scrubbed)
        self.assertIn("/root/GameManager", scrubbed)

    def test_godot4_transpilation(self):
        self.rules.auto_upgrade_annotations = True
        godot3_code = (
            "extends Node2D\n"
            "export var speed = 100\n"
            "onready var sprite = $Sprite\n"
            "var names: PoolStringArray = PoolStringArray()\n"
            "func _ready():\n"
            "    pass\n"
        )
        res = clean_content(godot3_code, rules=self.rules, file_path="character.gd")
        self.assertTrue(res.is_clean)
        self.assertIn("@export var", res.cleaned_content)
        self.assertIn("@onready var", res.cleaned_content)
        self.assertIn("PackedStringArray", res.cleaned_content)
        self.assertIn("godot4_transpiled", res.transformations)


if __name__ == "__main__":
    unittest.main()
