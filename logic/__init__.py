"""Root logic package."""
import sys
from pathlib import Path

# Automatically ensure src/ is on sys.path when imported as logic
src_path = str(Path(__file__).parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
