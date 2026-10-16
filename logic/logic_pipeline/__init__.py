"""Wrapper package exposing src/logic_pipeline."""
import sys
from pathlib import Path

src_pkg = Path(__file__).resolve().parent.parent / "src" / "logic_pipeline"
__path__ = [str(src_pkg)]

src_parent = str(Path(__file__).resolve().parent.parent / "src")
if src_parent not in sys.path:
    sys.path.insert(0, src_parent)
