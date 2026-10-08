"""UI-neutral application boundary shared by desktop front ends."""
from __future__ import annotations

import os
import re
import io
import json
import shutil
import subprocess
import logging
import tempfile
import uuid
import hashlib
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from huion.ble import load_config, save_config
from huion.ink import INK, stroke_colors, validate_color

from . import htr
from .enums import NoteCategory, NoteStatus
from .frontmatter import build_frontmatter, render_frontmatter, parse_frontmatter
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
    error: str = ""


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
        self.live_background: str | None = None

    def _user_config(self) -> dict:
        config = load_config()
        return config if isinstance(config, dict) else {}

    def _save_user_config(self, config: dict) -> None:
        save_config(config)
        from huion.ble import CONFIG_PATH
        os.chmod(CONFIG_PATH, 0o600)

    @property
    def auto_sync(self) -> bool:
        return bool(self._user_config().get("auto_sync", False))

    def set_auto_sync(self, enabled: bool) -> None:
        config = self._user_config()
        config["auto_sync"] = bool(enabled)
        self._save_user_config(config)

    def note_metadata(self, note: Note) -> dict:
        """Return user-owned library metadata keyed by the stable absolute SVG path."""
        data = self._user_config().get("note_metadata", {})
        value = data.get(str(Path(note.svg_path).absolute()), {}) if isinstance(data, dict) else {}
        return value if isinstance(value, dict) else {}

    def update_note_metadata(self, note: Note, *, title: str, tags: list[str], collection: str,
                             favourite: bool, reviewed: bool | None = None) -> dict:
        clean_title = " ".join(title.split())[:120]
        clean_tags = list(dict.fromkeys(" ".join(tag.split())[:40] for tag in tags if tag.strip()))[:12]
        clean_collection = " ".join(collection.split())[:60]
        config = self._user_config()
        all_metadata = config.setdefault("note_metadata", {})
        key = str(Path(note.svg_path).absolute())
        previous = all_metadata.get(key, {}) if isinstance(all_metadata.get(key), dict) else {}
        value = {"title": clean_title, "tags": clean_tags, "collection": clean_collection,
                 "favourite": bool(favourite), "reviewed": previous.get("reviewed", False) if reviewed is None else bool(reviewed)}
        all_metadata[key] = value
        self._save_user_config(config)
        return value

    @property
    def mac_address(self) -> str:
        return load_config().get("mac_address") or ""

    @property
    def output_directory(self) -> str:
        return self.config.output_directory

    @property
    def gemini_key(self) -> str:
        return os.environ.get("GEMINI_API_KEY") or load_config().get("gemini_key", "")

    @property
    def obsidian_vault(self) -> str:
        return str(self._user_config().get("obsidian_vault", ""))

    def save_settings(self, output_directory: str, gemini_key: str, mac_address: str | None = None,
                      pin: str | None = None, obsidian_vault: str | None = None) -> None:
        if not output_directory.strip():
            raise ValueError("Choose a notes folder.")
        if mac_address and not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", mac_address):
            raise ValueError("Use a Bluetooth address such as AA:BB:CC:DD:EE:FF, or leave it empty for discovery.")
        if pin and not re.fullmatch(r"\d{6}", pin):
            raise ValueError("The optional notebook PIN must contain six digits.")
        vault = os.path.expanduser(obsidian_vault.strip()) if obsidian_vault else ""
        if vault and (not Path(vault).is_dir() or not (Path(vault) / ".obsidian").is_dir()):
            raise ValueError("Choose an Obsidian vault folder containing .obsidian, or leave it empty.")
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
        if obsidian_vault is not None:
            cfg["obsidian_vault"] = vault
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
        address = getattr(getattr(self.bridge, "_current_conn", None), "mac", None)
        if not isinstance(address, str) or not address:
            address = self.mac_address
        storage = self._storage if isinstance(self._storage, dict) else {}
        count = storage.get("stored_pages")
        valid = (isinstance(count, int) and not isinstance(count, bool) and count >= 0
                 and bool(address) and storage.get("address") == address.upper())
        return DeviceSnapshot(
            connected=True if alive and getattr(self.bridge, "_is_connected", False) else None if alive else False,
            battery=getattr(self.bridge, "_last_battery", None),
            stored_pages=count if valid else None,
            storage_checked_at=str(storage.get("checked_at", "")) if valid else "",
            error=str(getattr(self.bridge, "_last_error", "") or ""),
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

    def start_notes(self) -> None:
        self.bridge.stream_pen_input(self.mac_address, mode="notes")

    def retry_connection(self, live: bool = False) -> None:
        self.bridge.retry_connection(self.mac_address, mode="tablet" if live else "notes")

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
            background = data.get("background_image")
            if background not in (None, ".live-background.jpg"):
                raise ValueError("The saved page image reference is invalid.")
            candidate = Path(self.output_directory) / background if background else None
            self.live_background = str(candidate) if candidate and candidate.is_file() else None
        except ValueError:
            self._draft_invalid = True
            raise ValueError("The saved live page metadata is invalid; the draft has been left untouched.")
        return strokes

    def import_live_background(self, source: str) -> str:
        """Normalize a user image into the current recoverable live draft."""
        from PIL import Image, ImageOps
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(source)
        folder = Path(self.output_directory)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / ".live-background.jpg"
        try:
            with Image.open(source_path) as opened:
                if opened.width * opened.height > 80_000_000:
                    raise ValueError("This image is too large. Choose one under 80 megapixels.")
                image = ImageOps.exif_transpose(opened).convert("RGB")
                image.thumbnail((2820, 3740), Image.Resampling.LANCZOS)
                with tempfile.NamedTemporaryFile(suffix=".jpg", dir=folder, delete=False) as tmp:
                    image.save(tmp, format="JPEG", quality=92, optimize=True)
                    tmp.flush()
                    os.fsync(tmp.fileno())
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("This image could not be opened. Choose a valid JPEG, PNG, WebP, BMP or TIFF file.") from exc
        os.replace(tmp.name, target)
        self.live_background = str(target)
        return self.live_background

    def adjust_live_background(self, *, rotate: int = 0, crop_to_page: bool = False,
                               opacity: int = 100, position: str = "centre") -> str:
        """Adjust only HuionNote's working copy; the imported source is never changed."""
        if not self.live_background or not Path(self.live_background).is_file():
            raise ValueError("Add a page image before adjusting it.")
        from PIL import Image, ImageOps
        path = Path(self.live_background)
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            if rotate:
                image = image.rotate(-rotate, expand=True, resample=Image.Resampling.BICUBIC)
            if crop_to_page:
                if position not in {"centre", "left", "right", "top", "bottom"}:
                    raise ValueError("Choose a valid crop position.")
                page_ratio = 28200 / 37400
                ratio = image.width / image.height
                if ratio > page_ratio:
                    width = round(image.height * page_ratio)
                    left = 0 if position == "left" else image.width - width if position == "right" else (image.width - width) // 2
                    image = image.crop((left, 0, left + width, image.height))
                elif ratio < page_ratio:
                    height = round(image.width / page_ratio)
                    top = 0 if position == "top" else image.height - height if position == "bottom" else (image.height - height) // 2
                    image = image.crop((0, top, image.width, top + height))
            opacity = max(10, min(100, int(opacity)))
            if opacity < 100:
                image = Image.blend(Image.new("RGB", image.size, "white"), image, opacity / 100)
            image.thumbnail((2820, 3740), Image.Resampling.LANCZOS)
            image.save(path, format="JPEG", quality=92, optimize=True)
        return str(path)

    def clear_live_background(self) -> None:
        if self.live_background:
            Path(self.live_background).unlink(missing_ok=True)
        self.live_background = None

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
                       "colors": colors, "ink_color": ink_color,
                       "background_image": Path(self.live_background).name
                       if self.live_background and Path(self.live_background).is_file() else None}, tmp)
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
        background = None
        if self.live_background and Path(self.live_background).is_file():
            from PIL import Image
            content = Path(self.live_background).read_bytes()
            with Image.open(io.BytesIO(content)) as image:
                background = ("image/jpeg", content, image.width, image.height)
        path.write_text(svg_document(strokes, self.live_colors, background), encoding="utf-8")
        path.with_suffix(".json").write_text(json.dumps({
            "page_width": 28200, "page_height": 37400, "max_pressure": 8192,
            "strokes": [{"color": color, "points": [{"x": x, "y": y, "pressure": p} for x, y, p in s]}
                        for s, color in zip(strokes, self.live_colors)],
            "background_image": {"embedded_in_svg": True, "mime_type": background[0],
                                 "width": background[2], "height": background[3]} if background else None,
        }), encoding="utf-8")
        return str(path)

    def new_live_page(self) -> None:
        self.clear_live_background()
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

    def sync_and_free_space(self, progress=None) -> list[Any]:
        """Save each page before the transport deletes that verified device page."""
        pages = self.bridge.sync_offline_pages(
            output_dir=self.output_directory,
            mac=self.mac_address,
            delete_after_export=True,
            force_vectors=True,
            progress=progress,
        )
        self._storage = {"address": self.mac_address.upper(), "stored_pages": 0,
                         "checked_at": datetime.now().astimezone().strftime("%d %b %Y, %H:%M")}
        config = self._user_config()
        config["storage_estimate"] = self._storage
        self._save_user_config(config)
        return pages

    def export_combined_pdf(self, notes: list[Note], destination: str, progress: Any = None) -> str:
        """Render selected vector pages into one portable multi-page PDF."""
        import cairosvg
        from PIL import Image
        if not notes:
            raise ValueError("Select at least one page.")
        images = []
        for index, note in enumerate(notes):
            image = Image.open(io.BytesIO(cairosvg.svg2png(url=note.svg_path, output_width=1410, output_height=1870))).convert("RGB")
            images.append(image)
            if progress:
                progress(index + 1, len(notes))
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        candidate, suffix = target, 1
        while candidate.exists():
            candidate = target.with_name(f"{target.stem}_{suffix}{target.suffix}")
            suffix += 1
        images[0].save(candidate, "PDF", save_all=True, append_images=images[1:], resolution=150)
        return str(candidate)

    @staticmethod
    def huion_id(note: Note) -> str:
        """A path-independent ID for stable Obsidian publishing."""
        stem = Path(note.svg_path).stem
        if stem.startswith("live_") and re.fullmatch(r"live_[A-Za-z0-9_]+", stem):
            return stem
        source = Path(note.json_path) if note.json_path and Path(note.json_path).is_file() else Path(note.svg_path)
        return f"huion-{hashlib.sha256(source.read_bytes()).hexdigest()[:20]}"

    @staticmethod
    def _obsidian_slug(title: str) -> str:
        normal = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().casefold()
        return re.sub(r"[^a-z0-9]+", "-", normal).strip("-")[:80] or "untitled-note"

    @staticmethod
    def _transcript_body(note: Note) -> str:
        if not note.markdown_path or not Path(note.markdown_path).is_file():
            return ""
        text = Path(note.markdown_path).read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            text = parts[2].lstrip() if len(parts) == 3 else text
        lines = text.splitlines()
        if lines and lines[0].startswith("# "):
            lines = lines[1:]
        return "\n".join(lines).strip()

    @staticmethod
    def _published_note_with_id(folder: Path, huion_id: str) -> Path | None:
        matches = []
        for path in folder.glob("*.md"):
            try:
                properties = parse_frontmatter(path.read_text(encoding="utf-8")[:4096])
            except OSError:
                continue
            if properties and properties.get("huion_id") == huion_id:
                matches.append(path)
        if len(matches) > 1:
            raise RuntimeError(f"More than one Obsidian note has huion_id {huion_id}. Resolve the duplicate before publishing.")
        return matches[0] if matches else None

    def publish_to_obsidian(self, notes: list[Note], progress: Any = None) -> list[str]:
        """Publish mobile-friendly notes without exposing HuionNote's raw library."""
        import cairosvg
        import yaml
        if not notes:
            raise ValueError("Select at least one saved page.")
        vault = Path(self.obsidian_vault).expanduser()
        if not vault.is_dir() or not (vault / ".obsidian").is_dir():
            raise ValueError("Choose your Obsidian vault in Settings before publishing.")
        inbox = vault / "00 Inbox" / "Huion"
        attachments = vault / "00 Inbox" / "Huion Attachments"
        inbox.mkdir(parents=True, exist_ok=True)
        attachments.mkdir(parents=True, exist_ok=True)
        published = []
        for index, note in enumerate(notes):
            source = Path(note.svg_path)
            if not source.is_file():
                raise FileNotFoundError(source)
            metadata = self.note_metadata(note)
            title = metadata.get("title") or source.stem.replace("_", " ").title()
            stable_id = self.huion_id(note)
            existing = self._published_note_with_id(inbox, stable_id)
            target = existing or inbox / f"{note.synced_at:%Y-%m-%d}-{self._obsidian_slug(title)}.md"
            if target.exists() and existing is None:
                raise FileExistsError(
                    f"{target.name} already exists with a different Huion ID. Rename it or change this page title; nothing was overwritten.")
            image = attachments / f"{stable_id}.png"
            png = cairosvg.svg2png(url=str(source), output_width=1410, output_height=1870)
            properties = {
                "title": title,
                "date": note.synced_at.date(),
                "source": "huion",
                "huion_id": stable_id,
                "status": "inbox",
                "tags": metadata.get("tags", []),
                "collection": metadata.get("collection", ""),
                "favourite": bool(metadata.get("favourite", False)),
                "reviewed": bool(metadata.get("reviewed", False)),
            }
            body = self._transcript_body(note)
            markdown = "---\n" + yaml.safe_dump(properties, sort_keys=False, allow_unicode=True) + "---\n"
            markdown += f"# {title}\n\n"
            if body:
                markdown += body + "\n\n"
            markdown += f"![[{stable_id}.png]]\n"
            for path, content in ((image, png), (target, markdown.encode("utf-8"))):
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
                    temporary.write(content)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary.name, path)
            published.extend((str(target), str(image)))
            if progress:
                progress(index + 1, len(notes))
        return published

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
                else htr.convert_local(note.svg_path, title=title)
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
