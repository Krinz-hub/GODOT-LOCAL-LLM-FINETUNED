"""Wrapper CLI forwarding to src/logic_pipeline/cli.py."""
import sys
from pathlib import Path

src_path = str(Path(__file__).resolve().parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from logic_pipeline.cli import main

if __name__ == "__main__":
    sys.exit(main())
