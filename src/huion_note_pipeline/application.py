"""UI-neutral application boundary shared by desktop front ends."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from huion.ble import load_config, save_config

from . import htr
from .enums import NoteCategory, NoteStatus
from .frontmatter import build_frontmatter, render_frontmatter
from .models import ConversionResult, Note
from .pipeline import NoteRegistry, SyncPipeline
from .store import CollisionResolver, JsonStore, MarkdownStore, SvgStore


@dataclass(frozen=True)
class DeviceSnapshot:
    connected: Optional[bool]
    battery: Optional[int]


class HuionApplication:
    """Owns hardware and note workflows; UI code only calls this public API."""

    def __init__(self, pipeline: SyncPipeline, bridge: Any) -> None:
        self.pipeline = pipeline
        self.bridge = bridge
        self.registry: NoteRegistry = pipeline.registry
        self.config = pipeline.config

    @property
    def mac_address(self) -> str:
        return load_config().get("mac_address") or "25:6C:BB:8D:19:50"

    @property
    def output_directory(self) -> str:
        return self.config.output_directory

    @property
    def gemini_key(self) -> str:
        return os.environ.get("GEMINI_API_KEY", "")

    def save_settings(self, output_directory: str, gemini_key: str) -> None:
        self.config.output_directory = os.path.expanduser(output_directory)
        self.pipeline.svg_store = SvgStore(self.config.output_directory)
        self.pipeline.json_store = JsonStore(self.config.output_directory)
        self.pipeline.markdown_store = MarkdownStore(self.config.output_directory)
        self.pipeline.collision_resolver = CollisionResolver(self.config.output_directory)
        cfg = load_config()
        cfg["output_dir"] = self.config.output_directory
        save_config(cfg)
        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key

    def device_snapshot(self) -> DeviceSnapshot:
        thread = getattr(self.bridge, "_stream_thread", None)
        alive = bool(thread and thread.is_alive())
        return DeviceSnapshot(
            connected=True if alive and getattr(self.bridge, "_is_connected", False) else None if alive else False,
            battery=getattr(self.bridge, "_last_battery", None),
        )

    def start_stream(self) -> None:
        self.bridge.stream_pen_input(self.mac_address, mode="tablet")

    def retry_connection(self) -> None:
        self.bridge.retry_connection(self.mac_address)

    def stop(self) -> None:
        self.bridge.stop_pen_input()

    def on_pen_point(self, callback: Any) -> None:
        self.bridge.on_pen_point(callback)

    def on_hardware_button(self, callback: Any) -> None:
        self.bridge.on_hardware_button(callback)

    def sync(self) -> list[Any]:
        return self.bridge.sync_offline_pages(
            output_dir=self.output_directory,
            mac=self.mac_address,
            delete_after_export=False,
        )

    def clear_device(self) -> None:
        from .ble_bridge import X10Device

        self.bridge.clear_all_pages(X10Device(address=self.mac_address))

    def load_notes(self) -> list[Note]:
        directories: Iterable[str] = (
            self.output_directory,
            os.path.expanduser("~/HuionNotes"),
            "./notes_output",
            "./exported_notes",
        )
        self.registry.load_from_disk(list(directories))
        return sorted(self.registry.all(), key=lambda note: note.synced_at, reverse=True)

    def save_markdown(self, note: Note, markdown: str) -> Note:
        if note.status == NoteStatus.CONVERTED and note.markdown_path:
            Path(note.markdown_path).write_text(markdown, encoding="utf-8")
            return note
        if note.status == NoteStatus.FAILED:
            self.pipeline.user_retries_note(object(), note)
        if note.status == NoteStatus.CONVERTING:
            raise RuntimeError("This note is already being converted.")
        if not self.pipeline.begin_conversion(note):
            raise RuntimeError("This note has reached its conversion retry limit.")
        title = Path(note.svg_path).stem.replace(" ", "_").lower()
        self.pipeline.conversion_succeeded(note, ConversionResult(
            success=True,
            derived_title=title,
            category=note.category or NoteCategory.UNCLASSIFIED,
            markdown=markdown,
        ))
        return note

    def convert(self, note: Note, cloud: bool = False, on_started: Any = None) -> Note:
        if not Path(note.svg_path).exists():
            raise FileNotFoundError(note.svg_path)
        if note.status == NoteStatus.FAILED:
            self.pipeline.user_retries_note(object(), note)
        if note.status == NoteStatus.CONVERTING:
            raise RuntimeError("This note is already being converted.")
        if note.status == NoteStatus.CONVERTED:
            raise RuntimeError("This note has already been converted.")
        if not self.pipeline.begin_conversion(note):
            raise RuntimeError("This note has reached its conversion retry limit.")
        if on_started:
            on_started(note)
        try:
            title = Path(note.svg_path).stem.replace("_", " ").title()
            raw, markdown = (
                htr.convert_gemini(note.svg_path, title=title, api_key=self.gemini_key)
                if cloud
                else htr.convert_tesseract(note.svg_path, title=title)
            )
            first_line = next((line.strip() for line in raw.splitlines() if line.strip()), title)
            derived = re.sub(r"[^\w\s-]", "", first_line).strip().replace(" ", "_").lower()[:40] or "note"
            category = NoteCategory.WORK if re.search(r"\bcyclops\b", raw, re.I) else NoteCategory.PERSONAL
            frontmatter = render_frontmatter(build_frontmatter(
                title=derived.replace("_", " ").title(),
                sync_date=(note.synced_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d"),
                category=category,
                tags=["engineering"] if category == NoteCategory.WORK else ["notes"],
            ))
            result = ConversionResult(
                success=True,
                derived_title=derived,
                category=category,
                markdown=f"{frontmatter}\n{markdown}\n\n![Note Sketch]({Path(note.svg_path).name})\n",
            )
            self.pipeline.conversion_succeeded(note, result)
            return note
        except Exception as exc:
            self.pipeline.conversion_failed(note, ConversionResult(success=False, error=str(exc)))
            raise
