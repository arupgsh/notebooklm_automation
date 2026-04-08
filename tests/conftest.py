import sys
from pathlib import Path


# Ensure src-layout modules are importable in tests without installation.
sys.path.insert(0, str((Path(__file__).resolve().parents[1] / "src")))
