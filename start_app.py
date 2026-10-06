#!/usr/bin/env python3
"""HuionNote Desktop Application Entry Point."""
import os
import sys
from pathlib import Path

# Add src/ directory to Python module search path
REPO_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_DIR / "src"))

from huion_note_pipeline.pipeline import SyncPipeline, NoteRegistry
from huion_note_pipeline.config import PipelineConfig
from huion_note_pipeline.store import SvgStore, JsonStore, MarkdownStore, CollisionResolver
from huion_note_pipeline.gui.qt_app import HuionNoteWindow
from huion_note_pipeline.ble_bridge import DeviceBridge


def main() -> None:
    # 1. Output directory: shared SVG/JSON/Markdown note library
    default_notes_dir = os.environ.get(
        "HUION_NOTES_DIR",
        str(Path.home() / "HuionNotes")
    )
    os.makedirs(default_notes_dir, exist_ok=True)

    # 2. Setup config
    config = PipelineConfig(output_directory=default_notes_dir)

    # 3. Initialize dependencies
    registry = NoteRegistry()
    svg_store = SvgStore(config.output_directory)
    json_store = JsonStore(config.output_directory)
    markdown_store = MarkdownStore(config.output_directory)
    collision_resolver = CollisionResolver(config.output_directory)

    # 4. Initialize pipeline engine
    pipeline = SyncPipeline(
        config=config,
        registry=registry,
        svg_store=svg_store,
        json_store=json_store,
        markdown_store=markdown_store,
        collision_resolver=collision_resolver,
    )

    # 5. Initialize Hardware Bridge
    bridge = DeviceBridge()
    bridge.attach_pipeline(pipeline)

    # 6. Launch the GUI; the application service resolves and starts the device.
    HuionNoteWindow.run(pipeline=pipeline, bridge=bridge)


if __name__ == "__main__":
    main()
