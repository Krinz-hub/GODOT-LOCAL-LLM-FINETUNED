"""Automated test suite for Godot Logic Pipeline."""
import sys
from pathlib import Path

# Automatically add logic/src to sys.path for test discovery
src_dir = str(Path(__file__).resolve().parent.parent / "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
