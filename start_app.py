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
from huion_note_pipeline.gui.app import HuionNotePipelineApp
from huion_note_pipeline.ble_bridge import DeviceBridge


def main() -> None:
    # 1. Output directory: CYC-Caleb Obsidian Raw PNGs inbox
    default_notes_dir = os.environ.get(
        "HUION_NOTES_DIR",
        str(Path.home() / "Documents" / "CYC-Caleb" / "00 Inbox" / "Raw PNGs")
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

    # 6. Start BLE Telemetry Engine
    mac_addr = "25:6C:BB:8D:19:50"
    print(f"[BLE] Starting Tablet Inking telemetry engine for {mac_addr}...")
    bridge.stream_pen_input(mac_addr, mode="tablet")

    # 7. Launch the GUI
    app = HuionNotePipelineApp(pipeline=pipeline, bridge=bridge)
    app.run()


if __name__ == "__main__":
    main()
