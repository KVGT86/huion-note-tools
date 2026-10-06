"""Core pipeline rules.

Spec source: huion-note-pipeline.allium

Each public method on NoteRegistry / SyncPipeline implements one rule from the spec.
Method names map directly to rule names in the spec.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Dict

from .config import PipelineConfig
from .enums import NoteStatus, NoteCategory
from .models import Note, ConversionAttempt, ConversionResult, NoteFilename
from .store import SvgStore, JsonStore, MarkdownStore, CollisionResolver


class NoteRegistry:
    """In-memory registry of all Note entities."""

    def __init__(self) -> None:
        self._notes: List[Note] = []
        self._by_page_id: Dict[str, Note] = {}

    def all(self) -> List[Note]:
        return list(self._notes)

    def add(self, note: Note, page_id: Optional[str] = None) -> None:
        self._notes.append(note)
        if page_id:
            self._by_page_id[page_id] = note

    def find_by_page_id(self, page_id: str) -> Optional[Note]:
        return self._by_page_id.get(page_id)

    def load_from_disk(self, directories: str | List[str]) -> List[Note]:
        """Scan directory or directories recursively for existing SVG/JSON/MD notes and register them."""
        import os
        from pathlib import Path

        if isinstance(directories, (str, Path)):
            dir_list = [directories]
        else:
            dir_list = list(directories)

        loaded: List[Note] = []
        registered_paths = {str(Path(n.svg_path).resolve()) for n in self._notes if n.svg_path}

        for d in dir_list:
            dir_path = Path(os.path.expanduser(str(d)))
            if not dir_path.exists():
                continue

            # Recursively find all .svg files
            svg_files = [f for f in dir_path.rglob("*.svg") if not f.name.endswith(".bak.svg")]
            for svg_f in sorted(svg_files, key=lambda f: f.stat().st_mtime, reverse=True):
                resolved_svg = str(svg_f.resolve())
                if resolved_svg in registered_paths:
                    continue

                page_id = resolved_svg
                if self.find_by_page_id(page_id):
                    continue

                json_candidate = svg_f.with_suffix(".json")
                if not json_candidate.exists():
                    json_candidate = svg_f.parent / "json" / f"{svg_f.stem}.json"
                json_path = str(json_candidate.resolve()) if json_candidate.exists() else None

                # Check if converted Markdown already exists
                md_candidate = svg_f.with_suffix(".md")
                if not md_candidate.exists():
                    md_candidate = svg_f.parent / "markdown" / f"{svg_f.stem}.md"
                md_path = str(md_candidate.resolve()) if md_candidate.exists() else None

                # Infer category from directory name
                parent_name = svg_f.parent.name.lower()
                if parent_name == "work":
                    cat = NoteCategory.WORK
                elif parent_name == "personal":
                    cat = NoteCategory.PERSONAL
                else:
                    cat = NoteCategory.UNCLASSIFIED

                stat = svg_f.stat()
                synced_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

                note = Note(
                    svg_path=resolved_svg,
                    json_path=json_path or resolved_svg,
                    synced_at=synced_at,
                    category=cat,
                    status=NoteStatus.CONVERTED if md_path else NoteStatus.SYNCED,
                    markdown_path=md_path,
                )
                self.add(note, page_id=page_id)
                registered_paths.add(resolved_svg)
                loaded.append(note)
        return loaded


class SyncPipeline:
    """Implements all spec rules that mutate Note state."""

    def __init__(
        self,
        config: PipelineConfig,
        registry: NoteRegistry,
        svg_store: SvgStore,
        json_store: JsonStore,
        markdown_store: MarkdownStore,
        collision_resolver: CollisionResolver,
    ) -> None:
        self.config = config
        self.registry = registry
        self.svg_store = svg_store
        self.json_store = json_store
        self.markdown_store = markdown_store
        self.collision_resolver = collision_resolver

    # ── Spec rule: AutoDetectAndSync ──────────────────────────────────────────

    def auto_detect_and_sync(self, device: object) -> List[Note]:
        """Spec: when DeviceDetected(device) → create Note per page (idempotent).

        SVG and JSON are written to disk before Note record is created.
        Pages are NOT deleted from the device.
        """
        synced_notes: List[Note] = []
        pages = getattr(device, "stored_pages", [])
        for page in pages:
            page_id = getattr(page, "page_id", "")
            if page_id and self.registry.find_by_page_id(page_id) is not None:
                continue
            svg_path = self.svg_store.write(page)
            json_path = self.json_store.write(page)
            note = Note(
                svg_path=svg_path,
                json_path=json_path,
                attempt_count=0,
                synced_at=datetime.now(timezone.utc),
                status=NoteStatus.SYNCED,
            )
            self.registry.add(note, page_id=page_id)
            synced_notes.append(note)
        return synced_notes

    # ── Spec rule: ManualSyncTriggered ──────────────────────────────────────────

    def manual_sync(self, user: object, device: object) -> List[Note]:
        """Spec: when UserRequestsSync(user, device) → same as AutoDetectAndSync."""
        return self.auto_detect_and_sync(device)

    # ── Spec rule: BeginConversion ──────────────────────────────────────────────

    def begin_conversion(self, note: Note) -> bool:
        """Spec: when Note.status becomes synced AND attempt_count < max.

        Returns True if conversion was started, False if attempt_count guard
        prevented it (note stays in synced, caller should mark it failed).
        """
        if note.status not in (NoteStatus.SYNCED, NoteStatus.CONVERTING):
            return False
        if note.attempt_count >= self.config.max_conversion_attempts:
            return False
        note.status = NoteStatus.CONVERTING
        note.attempt_count += 1
        now = datetime.now(timezone.utc)
        note.last_attempt = ConversionAttempt(attempted_at=now, succeeded=False)
        return True

    # ── Spec rule: ConversionSucceeded ────────────────────────────────────────────

    def conversion_succeeded(self, note: Note, result: ConversionResult) -> None:
        """Spec: when AntigravityConversionComplete(note, result) AND success=True.

        Sets note to converted; populates category, filename, markdown_path,
        converted_at, last_attempt.
        """
        if note.status != NoteStatus.CONVERTING:
            raise ValueError("Note must be in converting status")
        if not result.success:
            raise ValueError("Conversion result must be successful")

        note.status = NoteStatus.CONVERTED
        note.category = result.category if result.category is not None else NoteCategory.UNCLASSIFIED
        title = result.derived_title if result.derived_title is not None else "untitled"
        synced_at = note.synced_at or datetime.now(timezone.utc)
        date_str = synced_at.strftime("%d%m%Y")
        collision_idx = self.collision_resolver.index_for(synced_at, title, note.category)
        note.filename = NoteFilename(
            date_part=date_str,
            title_part=title,
            collision_index=collision_idx,
        )
        md_content = result.markdown if result.markdown is not None else ""
        note.markdown_path = self.markdown_store.write(md_content, note.category, note.filename)
        self.markdown_store.write_svg_backup(note.svg_path, note.category, note.filename)
        now = datetime.now(timezone.utc)
        note.converted_at = now
        note.last_attempt = ConversionAttempt(attempted_at=now, succeeded=True)

    # ── Spec rule: ConversionFailed ───────────────────────────────────────────────

    def conversion_failed(self, note: Note, result: ConversionResult) -> None:
        """Spec: when AntigravityConversionComplete(note, result) AND success=False.

        If attempt_count < max: status → synced (auto-retry), last_attempt = None.
        Else: status → failed, last_attempt recorded.
        """
        if note.status != NoteStatus.CONVERTING:
            raise ValueError("Note must be in converting status")
        if result.success:
            raise ValueError("Conversion result must be a failure")

        if note.attempt_count < self.config.max_conversion_attempts:
            note.status = NoteStatus.SYNCED
            note.last_attempt = None
        else:
            note.status = NoteStatus.FAILED
            now = datetime.now(timezone.utc)
            note.last_attempt = ConversionAttempt(
                attempted_at=now,
                succeeded=False,
                error_message=result.error,
            )

    # ── Spec rule: UserRetriesNote ──────────────────────────────────────────────

    def user_retries_note(self, user: object, note: Note) -> None:
        """Spec: when UserRetriesNote(user, note) AND status = failed.

        Resets status → synced, attempt_count → 0, last_attempt → None.
        Manual retries are unlimited.
        """
        if note.status != NoteStatus.FAILED:
            raise ValueError("Note must be in failed status to retry")
        note.status = NoteStatus.SYNCED
        note.attempt_count = 0
        note.last_attempt = None

    # ── Spec rule: ClearSyncedPages ─────────────────────────────────────────────

    def clear_synced_pages(self, user: object, device: object) -> None:
        """Spec: when UserClearsSyncedPages(user, device).

        Removes pages from device that have a Note record (any status).
        """
        pages = getattr(device, "stored_pages", None)
        if pages is not None:
            device.stored_pages = [
                p for p in pages if self.registry.find_by_page_id(getattr(p, "page_id", "")) is None
            ]
            if hasattr(device, "page_count"):
                device.page_count = len(device.stored_pages)

    # ── Spec rule: ClearAllPages ────────────────────────────────────────────────

    def clear_all_pages(self, user: object, device: object) -> None:
        """Spec: when UserClearsAllPages(user, device).

        Clears ALL pages from device regardless of sync status.
        GUI must have confirmed this with the user before calling.
        """
        pages = getattr(device, "stored_pages", None)
        if pages is not None:
            pages.clear()
            if hasattr(device, "page_count"):
                device.page_count = 0
