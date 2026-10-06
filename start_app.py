#!/usr/bin/env python3
"""HuionNote source-tree launcher; installed launchers use the same entry point."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from huion_note_pipeline.gui.qt_app import main

if __name__ == "__main__":
    raise SystemExit(main())
