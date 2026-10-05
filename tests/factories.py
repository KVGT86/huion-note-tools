"""Test factories for Note entities and related value objects.

Factories create entities in a specific lifecycle state with all required
spec-mandated fields present. Using factories ensures tests don't accidentally
produce invalid states.

Spec reference:
  Note state-dependent fields:
    markdown_path, category, filename, converted_at → when status = converted
    last_attempt → when status in (converting, converted, failed)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List

from huion_note_pipeline.enums import NoteCategory, NoteStatus
from huion_note_pipeline.models import (
    Note, NoteFilename, ConversionAttempt, ConversionResult,
)

ANCHOR = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)


def make_filename(
    date_part: str = "21082026",
    title_part: str = "test_note",
    collision_index: Optional[int] = None,
) -> NoteFilename:
    return NoteFilename(
        date_part=date_part,
        title_part=title_part,
        collision_index=collision_index,
    )


def make_attempt(
    succeeded: bool = True,
    at: datetime = ANCHOR,
    error: Optional[str] = None,
) -> ConversionAttempt:
    return ConversionAttempt(
        attempted_at=at,
        succeeded=succeeded,
        error_message=error,
    )


def make_conversion_result(
    success: bool = True,
    title: str = "test_note",
    category: NoteCategory = NoteCategory.PERSONAL,
    markdown: str = "---\ntitle: Test\ndate: 2026-08-21\ncategory: personal\ntags: []\n---\n",
    tags: Optional[List[str]] = None,
    error: Optional[str] = None,
) -> ConversionResult:
    return ConversionResult(
        success=success,
        derived_title=title if success else None,
        category=category if success else None,
        markdown=markdown if success else None,
        tags=tags or [] if success else None,
        error=error if not success else None,
    )


def make_synced_note(
    svg_path: str = "/tmp/test.svg",
    json_path: str = "/tmp/test.json",
    attempt_count: int = 0,
    synced_at: datetime = ANCHOR,
) -> Note:
    """A Note in the 'synced' state — all when-fields are absent."""
    return Note(
        svg_path=svg_path,
        json_path=json_path,
        attempt_count=attempt_count,
        synced_at=synced_at,
        status=NoteStatus.SYNCED,
        # when-fields absent (status not in qualifying set)
        markdown_path=None,
        category=None,
        filename=None,
        converted_at=None,
        last_attempt=None,
    )


def make_converting_note(
    attempt_count: int = 1,
    synced_at: datetime = ANCHOR,
) -> Note:
    """A Note in the 'converting' state."""
    note = make_synced_note(synced_at=synced_at)
    note.status = NoteStatus.CONVERTING
    note.attempt_count = attempt_count
    note.last_attempt = make_attempt(succeeded=False)
    return note


def make_converted_note(
    category: NoteCategory = NoteCategory.PERSONAL,
    title: str = "test_note",
    attempt_count: int = 1,
    synced_at: datetime = ANCHOR,
) -> Note:
    """A Note in the 'converted' state — all when-fields are present."""
    note = make_synced_note(synced_at=synced_at)
    note.status = NoteStatus.CONVERTED
    note.attempt_count = attempt_count
    note.category = category
    note.filename = make_filename(title_part=title)
    note.markdown_path = f"{category.value}/{note.filename.md_filename()}"
    note.converted_at = ANCHOR
    note.last_attempt = make_attempt(succeeded=True)
    return note


def make_failed_note(
    attempt_count: int = 2,
    error: str = "Conversion timed out",
    synced_at: datetime = ANCHOR,
) -> Note:
    """A Note in the 'failed' state (max auto-retries exhausted)."""
    note = make_synced_note(synced_at=synced_at)
    note.status = NoteStatus.FAILED
    note.attempt_count = attempt_count
    note.last_attempt = make_attempt(succeeded=False, error=error)
    return note
