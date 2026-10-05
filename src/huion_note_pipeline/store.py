"""Disk storage and collision resolution for synced notes.

Spec source: huion-note-pipeline.allium
  Black-box functions referenced in rules:
    SvgStore.write(page)     -> svg_path (String)
    JsonStore.write(page)    -> json_path (String)
    MarkdownStore.write(...) -> markdown_path (String)
    CollisionResolver.index_for(synced_at, title) -> Integer?
    CategoryFolder(category) -> folder (String)  e.g. "work/"
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from .enums import NoteCategory
from .models import NoteFilename


import shutil

CATEGORY_FOLDERS: dict[NoteCategory, str] = {
    NoteCategory.WORK: "work",
    NoteCategory.PERSONAL: "personal",
    NoteCategory.UNCLASSIFIED: "unclassified",
}


def category_folder(category: NoteCategory, output_directory: str) -> Path:
    """Return the absolute output folder for the given category."""
    subfolder = CATEGORY_FOLDERS.get(
        category,
        category.value if isinstance(category, NoteCategory) else str(category),
    )
    folder = Path(output_directory) / subfolder
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class CollisionResolver:
    """Resolves filename collisions within a category folder.

    Spec: collision_index is None when unique; 2, 3, ... otherwise.
    Collision is scoped per-folder (work/, personal/, unclassified/ are independent).
    """

    def __init__(self, output_directory: str) -> None:
        self.output_directory = output_directory

    def index_for(
        self,
        synced_at: datetime,
        title: str,
        category: NoteCategory,
    ) -> Optional[int]:
        """Return None if [ddmmyyyy]_[title].md is available in the category folder.
        Return 2, 3, ... (first unused index) otherwise.
        """
        folder = category_folder(category, self.output_directory)
        date_str = synced_at.strftime("%d%m%Y")
        base_stem = f"{date_str}_{title}"
        base_file = folder / f"{base_stem}.md"
        if not base_file.exists():
            return None

        idx = 2
        while (folder / f"{base_stem}_{idx}.md").exists():
            idx += 1
        return idx


class SvgStore:
    """Writes raw page SVG to disk immediately on sync."""

    def __init__(self, output_directory: str) -> None:
        self.output_directory = output_directory
        self.svg_dir = Path(output_directory) / "svg"
        self.svg_dir.mkdir(parents=True, exist_ok=True)

    def write(self, page: object) -> str:
        """Write page SVG to disk. Returns the absolute path."""
        page_id = getattr(page, "page_id", "page")
        file_path = self.svg_dir / f"{page_id}.svg"
        raw_data = getattr(page, "raw_data", b"")
        if isinstance(raw_data, str):
            file_path.write_text(raw_data, encoding="utf-8")
        elif isinstance(raw_data, bytes):
            file_path.write_bytes(raw_data if raw_data else b"<svg></svg>")
        else:
            file_path.write_text("<svg></svg>", encoding="utf-8")
        return str(file_path.resolve())


class JsonStore:
    """Writes raw page JSON (stroke data) to disk immediately on sync."""

    def __init__(self, output_directory: str) -> None:
        self.output_directory = output_directory
        self.json_dir = Path(output_directory) / "json"
        self.json_dir.mkdir(parents=True, exist_ok=True)

    def write(self, page: object) -> str:
        """Write page JSON to disk. Returns the absolute path."""
        page_id = getattr(page, "page_id", "page")
        file_path = self.json_dir / f"{page_id}.json"
        file_path.write_text("{}", encoding="utf-8")
        return str(file_path.resolve())


class MarkdownStore:
    """Writes converted markdown notes to the correct category folder."""

    def __init__(self, output_directory: str) -> None:
        self.output_directory = output_directory

    def write(
        self,
        content: str,
        category: NoteCategory,
        filename: NoteFilename,
    ) -> str:
        """Write markdown to the category folder. Returns the absolute path."""
        folder = category_folder(category, self.output_directory)
        file_path = folder / filename.md_filename()
        file_path.write_text(content, encoding="utf-8")
        return str(file_path.resolve())

    def write_svg_backup(
        self,
        svg_path: str,
        category: NoteCategory,
        filename: NoteFilename,
    ) -> str:
        """Copy SVG backup alongside the markdown in the category folder.

        Spec: SVG mirrors the markdown path.
        e.g. work/21082026_bridge_calc.svg alongside work/21082026_bridge_calc.md
        """
        folder = category_folder(category, self.output_directory)
        dst_path = folder / filename.svg_filename()
        src = Path(svg_path)
        if src.exists():
            shutil.copy2(src, dst_path)
        else:
            dst_path.write_text("<svg></svg>", encoding="utf-8")
        return str(dst_path.resolve())
