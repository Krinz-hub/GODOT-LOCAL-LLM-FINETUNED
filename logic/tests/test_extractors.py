import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import unittest

from logic_pipeline.extractors.project_config import parse_project_godot
from logic_pipeline.extractors.gdscript import parse_gdscript
from logic_pipeline.extractors.scene import parse_scene_file
from logic_pipeline.extractors.resource import parse_resource_file
from logic_pipeline.extractors.patches import parse_git_diff
from logic_pipeline.config import find_logic_root


class TestExtractors(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = find_logic_root() / "tests" / "fixtures" / "sample_project"

    def test_parse_project_godot(self):
        proj_file = self.fixtures_dir / "project.godot"
        with open(proj_file, "r", encoding="utf-8") as f:
            content = f.read()

        info = parse_project_godot(content)
        self.assertEqual(info.project_name, "Sample Godot Project")
        self.assertEqual(info.main_scene, "res://main.tscn")
        self.assertIn("4.3", info.godot_version)
        self.assertIn("GameManager", info.autoloads)
        self.assertEqual(info.autoloads["GameManager"], "res://game_manager.gd")

    def test_parse_gdscript(self):
        gd_file = self.fixtures_dir / "player.gd"
        with open(gd_file, "r", encoding="utf-8") as f:
            content = f.read()

        analysis = parse_gdscript(content)
        self.assertEqual(analysis.class_name, "Player")
        self.assertEqual(analysis.extends_class, "CharacterBody2D")
        self.assertIn("health_changed", analysis.signals)
        self.assertIn("died", analysis.signals)
        self.assertIn("speed", analysis.exported_properties)
        self.assertIn("take_damage", analysis.public_methods)
        self.assertIn("_physics_process", analysis.lifecycle_methods)
        self.assertFalse(analysis.has_godot3_syntax)

    def test_parse_scene_file(self):
        scene_file = self.fixtures_dir / "main.tscn"
        with open(scene_file, "r", encoding="utf-8") as f:
            content = f.read()

        analysis = parse_scene_file(content)
        self.assertEqual(analysis.root_node_name, "Main")
        self.assertEqual(analysis.root_node_type, "Node2D")
        self.assertEqual(analysis.attached_script, "res://game_manager.gd")
        self.assertIn("res://player.tscn", analysis.instanced_scenes)
        self.assertIn("Main (Node2D)", analysis.hierarchy_summary)

    def test_parse_resource_file(self):
        tres_file = self.fixtures_dir / "theme.tres"
        with open(tres_file, "r", encoding="utf-8") as f:
            content = f.read()

        analysis = parse_resource_file(content)
        self.assertEqual(analysis.resource_type, "Theme")
        self.assertEqual(analysis.format_version, 3)
        self.assertEqual(analysis.properties.get("default_font_size"), "16")

    def test_parse_git_diff(self):
        diff_text = """diff --git a/player.gd b/player.gd
--- a/player.gd
+++ b/player.gd
@@ -10,3 +10,4 @@
-    velocity.y = min(velocity.y + gravity * delta, 2000.0)
+    velocity.y = min(velocity.y + gravity * delta, 800.0)
"""
        patches = parse_git_diff(diff_text)
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0].old_path, "player.gd")
        self.assertEqual(patches[0].new_path, "player.gd")
        self.assertEqual(patches[0].added_lines, 1)
        self.assertEqual(patches[0].deleted_lines, 1)


if __name__ == "__main__":
    unittest.main()
