"""Entry point so `python smad.py ...` works from the repo root."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from smad.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
