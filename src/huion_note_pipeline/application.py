"""UI-neutral application boundary shared by desktop front ends."""
from __future__ import annotations

import os
import re
import json
import shutil
import subprocess
import logging
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from huion.ble import load_config, save_config
from huion.ink import INK, stroke_colors, validate_color

from . import htr
from .enums import NoteCategory, NoteStatus
from .frontmatter import build_frontmatter, render_frontmatter
from .models import ConversionResult, Note
from .pipeline import NoteRegistry, SyncPipeline
from .store import CollisionResolver, JsonStore, MarkdownStore, SvgStore


def create_application() -> "HuionApplication":
    """Compose the shared backend for either installed or source-tree launchers."""
    from huion.ble import CONFIG_PATH
    from .config import PipelineConfig
    from .ble_bridge import DeviceBridge
    folder = os.environ.get("HUION_NOTES_DIR") or (
        load_config().get("output_dir") if Path(CONFIG_PATH).exists() else None
    ) or str(Path.home() / "HuionNotes")
    Path(folder).mkdir(parents=True, exist_ok=True)
    config = PipelineConfig(folder)
    pipeline = SyncPipeline(config, NoteRegistry(), SvgStore(folder), JsonStore(folder),
                            MarkdownStore(folder), CollisionResolver(folder))
    bridge = DeviceBridge()
    bridge.attach_pipeline(pipeline)
    return HuionApplication(pipeline, bridge)


@dataclass(frozen=True)
class DeviceSnapshot:
    connected: Optional[bool]
    battery: Optional[int]
    stored_pages: Optional[int] = None
    storage_checked_at: str = ""


class HuionApplication:
    """Owns hardware and note workflows; UI code only calls this public API."""

    def __init__(self, pipeline: SyncPipeline, bridge: Any) -> None:
        self.pipeline = pipeline
        self.bridge = bridge
        self.registry: NoteRegistry = pipeline.registry
        self.config = pipeline.config
        self._storage = load_config().get("storage_estimate", {})
        self.live_colors: list[str] = []
        self.ink_color = INK

    @property
    def mac_address(self) -> str:
        return load_config().get("mac_address") or ""

    @property
    def output_directory(self) -> str:
        return self.config.output_directory

    @property
    def gemini_key(self) -> str:
        return os.environ.get("GEMINI_API_KEY") or load_config().get("gemini_key", "")

    def save_settings(self, output_directory: str, gemini_key: str, mac_address: str | None = None, pin: str | None = None) -> None:
        if not output_directory.strip():
            raise ValueError("Choose a notes folder.")
        if mac_address and not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", mac_address):
            raise ValueError("Use a Bluetooth address such as AA:BB:CC:DD:EE:FF, or leave it empty for discovery.")
        if pin and not re.fullmatch(r"\d{6}", pin):
            raise ValueError("The optional notebook PIN must contain six digits.")
        Path(os.path.expanduser(output_directory)).mkdir(parents=True, exist_ok=True)
        self.config.output_directory = os.path.expanduser(output_directory)
        self.pipeline.svg_store = SvgStore(self.config.output_directory)
        self.pipeline.json_store = JsonStore(self.config.output_directory)
        self.pipeline.markdown_store = MarkdownStore(self.config.output_directory)
        self.pipeline.collision_resolver = CollisionResolver(self.config.output_directory)
        cfg = load_config()
        cfg["output_dir"] = self.config.output_directory
        cfg["gemini_key"] = gemini_key
        if mac_address is not None:
            cfg["mac_address"] = mac_address.upper()
        if pin is not None:
            cfg["pin"] = pin
        save_config(cfg)
        from huion.ble import CONFIG_PATH
        os.chmod(CONFIG_PATH, 0o600)
        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
        else:
            os.environ.pop("GEMINI_API_KEY", None)

    def device_snapshot(self) -> DeviceSnapshot:
        thread = getattr(self.bridge, "_stream_thread", None)
        alive = bool(thread and thread.is_alive())
        address = getattr(getattr(self.bridge, "_current_conn", None), "mac", None) or self.mac_address
        storage = self._storage if isinstance(self._storage, dict) else {}
        count = storage.get("stored_pages")
        valid = (isinstance(count, int) and not isinstance(count, bool) and count >= 0
                 and bool(address) and storage.get("address") == address.upper())
        return DeviceSnapshot(
            connected=True if alive and getattr(self.bridge, "_is_connected", False) else None if alive else False,
            battery=getattr(self.bridge, "_last_battery", None),
            stored_pages=count if valid else None,
            storage_checked_at=str(storage.get("checked_at", "")) if valid else "",
        )

    def delete_notes(self, notes: list[Note]) -> list[str]:
        """Move selected local page files to the desktop Trash, never device memory."""
        registered = self.registry.all()
        if not notes or any(not any(n is known for known in registered) for n in notes):
            raise ValueError("Select saved pages from the library before deleting.")
        if any(n.status == NoteStatus.CONVERTING for n in notes):
            raise RuntimeError("Wait for transcription to finish before deleting these pages.")
        if not shutil.which("gio"):
            raise RuntimeError("Desktop Trash is unavailable. Install the system GIO tools; no files were deleted.")
        paths = set()
        for note in notes:
            paths.update(Path(p).absolute() for p in (note.svg_path, note.json_path, note.markdown_path) if p)
            if note.markdown_path:
                paths.add(Path(note.markdown_path).absolute().with_suffix(".svg"))
            if Path(note.json_path).suffix == ".json":
                paths.add(Path(note.svg_path).absolute().with_suffix(".png"))
        paths = sorted(p for p in paths if p.is_file())
        # Keep the current live draft, but a later Save must create a new page.
        if any(p.stem == getattr(self, "_live_id", None) for p in paths):
            strokes = self.live_draft()
            self._live_id = None
            self.save_live_draft(strokes)
        try:
            if paths:
                subprocess.run(["gio", "trash", "--", *(str(p) for p in paths)], check=True,
                               capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("Some files could not be moved to Trash. Check folder permissions. "
                               "Files already moved can be restored from Trash.\n" + exc.stderr) from exc
        finally:
            for note in registered:
                if not Path(note.svg_path).exists():
                    self.registry.remove(note)
        return [str(p) for p in paths]

    def start_stream(self) -> None:
        self.bridge.stream_pen_input(self.mac_address, mode="tablet")

    def retry_connection(self) -> None:
        self.bridge.retry_connection(self.mac_address)

    def stop(self) -> None:
        self.bridge.stop_pen_input()

    def live_draft(self) -> list[list[list[float]]]:
        path = Path(self.output_directory) / ".live-draft.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            strokes = data["strokes"]
        except Exception as exc:
            self._draft_invalid = True
            raise ValueError("The live draft could not be read. Its contents will be preserved in a recovery copy.") from exc
        import math
        if not isinstance(strokes, list) or any(
            not isinstance(s, list) or any(
                not isinstance(p, list) or len(p) != 3 or
                any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in p)
                for p in s) for s in strokes
        ):
            self._draft_invalid = True
            raise ValueError("The saved live draft is invalid; it has been left untouched.")
        self._live_id = data.get("page_id")
        if self._live_id and (not isinstance(self._live_id, str) or not re.fullmatch(r"live_[a-zA-Z0-9_]+", self._live_id)):
            self._draft_invalid = True
            self._live_id = None
            raise ValueError("The saved live draft has an invalid page ID.")
        try:
            self.live_colors = stroke_colors(len(strokes), data.get("colors"))
            self.ink_color = validate_color(data.get("ink_color", INK))
        except ValueError:
            self._draft_invalid = True
            raise ValueError("The saved ink colours are invalid; the draft has been left untouched.")
        return strokes

    def save_live_draft(self, strokes: list, colors: list[str] | None = None, ink_color: str | None = None) -> None:
        colors = stroke_colors(len(strokes), colors if colors is not None else
                               self.live_colors if len(self.live_colors) == len(strokes) else None)
        ink_color = validate_color(self.ink_color if ink_color is None else ink_color)
        if not getattr(self, "_live_id", None):
            self._live_id = f"live_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        folder = Path(self.output_directory)
        folder.mkdir(parents=True, exist_ok=True)
        if getattr(self, "_draft_invalid", False) and (folder / ".live-draft.json").exists():
            shutil.copyfile(folder / ".live-draft.json", folder / f".live-draft-recovery-{uuid.uuid4().hex}.json")
            self._draft_invalid = False
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, delete=False) as tmp:
            json.dump({"page_id": self._live_id, "strokes": strokes,
                       "colors": colors, "ink_color": ink_color}, tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp.name, folder / ".live-draft.json")
        self.live_colors, self.ink_color = colors, ink_color

    def save_live_page(self, strokes: list, colors: list[str] | None = None, ink_color: str | None = None) -> str:
        from huion.ink import svg_document
        self.save_live_draft(strokes, colors, ink_color)
        folder = Path(self.output_directory) / "Live"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self._live_id}.svg"
        path.write_text(svg_document(strokes, self.live_colors), encoding="utf-8")
        path.with_suffix(".json").write_text(json.dumps({
            "page_width": 28200, "page_height": 37400, "max_pressure": 8192,
            "strokes": [{"color": color, "points": [{"x": x, "y": y, "pressure": p} for x, y, p in s]}
                        for s, color in zip(strokes, self.live_colors)],
        }), encoding="utf-8")
        return str(path)

    def new_live_page(self) -> None:
        self._live_id = None
        self.save_live_draft([])

    def export_notes(self, notes: list[Note], destination: str, formats: list[str], progress: Any = None) -> list[str]:
        """Export without overwriting existing files; Qt stays outside this boundary."""
        import cairosvg
        if not formats or any(f not in {"svg", "png", "pdf", "json", "md"} for f in formats):
            raise ValueError("Choose at least one supported export format.")
        root = Path(destination).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        exported = []
        for index, note in enumerate(notes):
            source = Path(note.svg_path)
            note_root = root
            if "md" in formats and note.markdown_path:
                count = 0
                while True:
                    note_root = root / (source.stem + (f"_{count}" if count else ""))
                    try:
                        note_root.mkdir()
                        break
                    except FileExistsError:
                        count += 1
            for fmt in formats:
                if fmt in {"json", "md"}:
                    candidate = note.json_path if fmt == "json" else note.markdown_path
                    if not candidate or Path(candidate).suffix.lower() != f".{fmt}" or not Path(candidate).exists():
                        continue
                    content = Path(candidate).read_bytes()
                elif fmt == "svg":
                    content = source.read_bytes()
                elif fmt == "png":
                    content = cairosvg.svg2png(url=str(source), output_width=2820, output_height=3740)
                else:
                    content = cairosvg.svg2pdf(url=str(source), output_width=559.37, output_height=793.70)
                path = note_root / f"{source.stem}.{fmt}"
                count = 1
                while True:
                    try:
                        with path.open("xb") as out:
                            out.write(content)
                        break
                    except FileExistsError:
                        path = note_root / f"{source.stem}_{count}.{fmt}"
                        count += 1
                exported.append(str(path))
                if fmt == "md":
                    # Markdown companions keep relative sketch links usable.
                    for image in (source, Path(candidate).with_suffix(".svg")):
                        target = note_root / image.name
                        if image.exists() and not target.exists():
                            shutil.copyfile(image, target)
            if progress:
                progress(index + 1, len(notes))
        return exported

    def on_pen_point(self, callback: Any) -> None:
        self.bridge.on_pen_point(callback)

    def on_hardware_button(self, callback: Any) -> None:
        self.bridge.on_hardware_button(callback)

    def sync(self, progress=None) -> list[Any]:
        pages = self.bridge.sync_offline_pages(
            output_dir=self.output_directory,
            mac=self.mac_address,
            delete_after_export=False,
            force_vectors=True,
            progress=progress,
        )
        reading = getattr(self.bridge, "last_storage_sync", None)
        if isinstance(reading, tuple) and len(reading) == 2:
            address, count = reading
            self._storage = {"address": address.upper(), "stored_pages": count,
                             "checked_at": datetime.now().astimezone().strftime("%d %b %Y, %H:%M")}
            cfg = load_config()
            cfg["storage_estimate"] = self._storage
            try:
                save_config(cfg)
                from huion.ble import CONFIG_PATH
                os.chmod(CONFIG_PATH, 0o600)
            except OSError:
                logging.getLogger(__name__).warning("Storage estimate could not be saved; synced pages are safe.")
        return pages

    def clear_device(self) -> None:
        from .ble_bridge import X10Device

        self.bridge.clear_all_pages(X10Device(address=self.mac_address))
        self._storage = {}
        cfg = load_config()
        cfg.pop("storage_estimate", None)
        try:
            save_config(cfg)
            from huion.ble import CONFIG_PATH
            os.chmod(CONFIG_PATH, 0o600)
        except OSError:
            logging.getLogger(__name__).warning("Storage estimate reset could not be saved.")

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
