import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import unittest

from logic_pipeline.config import load_config, find_logic_root, AppConfig


class TestConfig(unittest.TestCase):
    def test_find_logic_root(self):
        root = find_logic_root()
        self.assertTrue(root.exists())
        self.assertTrue((root / "config").exists() or (root / "schemas").exists())

    def test_load_config_validity(self):
        config = load_config()
        self.assertIsInstance(config, AppConfig)
        self.assertTrue(config.pipeline.name.startswith("godot-logic"))
        self.assertEqual(config.pipeline.random_seed, 42)
        self.assertEqual(config.pipeline.train_ratio, 0.80)
        self.assertEqual(config.pipeline.val_ratio, 0.10)
        self.assertEqual(config.pipeline.test_ratio, 0.10)

    def test_sources_config(self):
        config = load_config()
        self.assertTrue(config.sources.local_enabled)
        self.assertFalse(config.sources.github_enabled)  # Off by default for safety
        self.assertIn("MIT", config.sources.github_allowed_licenses)

    def test_cleaning_rules(self):
        config = load_config()
        self.assertIn(".gd", config.cleaning.allowed_extensions)
        self.assertIn(".dll", config.cleaning.blocked_bloat)
        self.assertTrue(config.cleaning.redact_emails)
        self.assertTrue(config.cleaning.redact_local_paths)

    def test_validation_rules(self):
        config = load_config()
        self.assertTrue(config.validation.enforce_strict_schema)
        self.assertTrue(config.validation.verify_scene_paths)
        self.assertFalse(config.validation.allow_runtime_execution)  # Safe default


if __name__ == "__main__":
    unittest.main()
