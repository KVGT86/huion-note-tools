"""Tests for entity and value type structure.

Spec obligations covered:
  entity-fields.NoteFilename
  entity-fields.ConversionAttempt
  entity-fields.ConversionResult
  entity-fields.X10Device
  value-equality.NoteFilename
  value-equality.ConversionAttempt
  value-equality.ConversionResult
  when-set fields: present in qualifying states, absent outside
"""
from datetime import datetime, timezone
from typing import Optional

import pytest

from huion_note_pipeline.enums import NoteCategory, NoteStatus
from huion_note_pipeline.models import (
    Note, NoteFilename, ConversionAttempt, ConversionResult,
)
from tests.factories import (
    make_synced_note, make_converting_note, make_converted_note,
    make_failed_note, make_filename, make_attempt, ANCHOR,
)


# ---------------------------------------------------------------------------
# NoteFilename value type
# ---------------------------------------------------------------------------

class TestNoteFilename:
    def test_has_date_part(self):
        fn = make_filename(date_part="21082026")
        assert fn.date_part == "21082026"

    def test_has_title_part(self):
        fn = make_filename(title_part="bridge_calc")
        assert fn.title_part == "bridge_calc"

    def test_collision_index_defaults_to_none(self):
        fn = make_filename()
        assert fn.collision_index is None

    def test_collision_index_can_be_set(self):
        fn = make_filename(collision_index=2)
        assert fn.collision_index == 2

    def test_structural_equality(self):
        a = make_filename(date_part="21082026", title_part="notes", collision_index=None)
        b = make_filename(date_part="21082026", title_part="notes", collision_index=None)
        assert a == b

    def test_structural_inequality_different_title(self):
        a = make_filename(title_part="notes")
        b = make_filename(title_part="other")
        assert a != b

    def test_structural_inequality_different_collision_index(self):
        a = make_filename(collision_index=None)
        b = make_filename(collision_index=2)
        assert a != b

    def test_md_filename_no_index(self):
        fn = make_filename(date_part="21082026", title_part="bridge_calc", collision_index=None)
        assert fn.md_filename() == "21082026_bridge_calc.md"

    def test_md_filename_with_index(self):
        fn = make_filename(date_part="21082026", title_part="bridge_calc", collision_index=2)
        assert fn.md_filename() == "21082026_bridge_calc_2.md"

    def test_svg_filename_no_index(self):
        fn = make_filename(date_part="21082026", title_part="bridge_calc", collision_index=None)
        assert fn.svg_filename() == "21082026_bridge_calc.svg"

    def test_svg_filename_with_index(self):
        fn = make_filename(date_part="21082026", title_part="bridge_calc", collision_index=2)
        assert fn.svg_filename() == "21082026_bridge_calc_2.svg"


# ---------------------------------------------------------------------------
# ConversionAttempt value type
# ---------------------------------------------------------------------------

class TestConversionAttempt:
    def test_has_attempted_at(self):
        attempt = make_attempt(at=ANCHOR)
        assert attempt.attempted_at == ANCHOR

    def test_has_succeeded(self):
        attempt = make_attempt(succeeded=True)
        assert attempt.succeeded is True

    def test_error_message_defaults_to_none(self):
        attempt = make_attempt()
        assert attempt.error_message is None

    def test_error_message_present_on_failure(self):
        attempt = make_attempt(succeeded=False, error="Timeout")
        assert attempt.error_message == "Timeout"

    def test_structural_equality(self):
        a = ConversionAttempt(attempted_at=ANCHOR, succeeded=True, error_message=None)
        b = ConversionAttempt(attempted_at=ANCHOR, succeeded=True, error_message=None)
        assert a == b

    def test_structural_inequality(self):
        a = ConversionAttempt(attempted_at=ANCHOR, succeeded=True)
        b = ConversionAttempt(attempted_at=ANCHOR, succeeded=False)
        assert a != b


# ---------------------------------------------------------------------------
# ConversionResult value type
# ---------------------------------------------------------------------------

class TestConversionResult:
    def test_has_success_field(self):
        result = ConversionResult(success=True)
        assert result.success is True

    def test_has_derived_title(self):
        result = ConversionResult(success=True, derived_title="Notes")
        assert result.derived_title == "Notes"

    def test_has_category(self):
        result = ConversionResult(success=True, category=NoteCategory.WORK)
        assert result.category == NoteCategory.WORK

    def test_has_markdown(self):
        result = ConversionResult(success=True, markdown="# hello")
        assert result.markdown == "# hello"

    def test_has_tags(self):
        result = ConversionResult(success=True, tags=["engineering"])
        assert result.tags == ["engineering"]

    def test_has_error(self):
        result = ConversionResult(success=False, error="OCR failed")
        assert result.error == "OCR failed"

    def test_structural_equality(self):
        a = ConversionResult(success=True, derived_title="X")
        b = ConversionResult(success=True, derived_title="X")
        assert a == b


# ---------------------------------------------------------------------------
# Note entity — always-present fields
# ---------------------------------------------------------------------------

class TestNoteAlwaysPresentFields:
    """Spec invariant: SVGAlwaysPresent — svg_path is never None."""

    def test_synced_note_has_svg_path(self):
        note = make_synced_note(svg_path="/out/page-001.svg")
        assert note.svg_path == "/out/page-001.svg"

    def test_synced_note_has_json_path(self):
        note = make_synced_note(json_path="/out/page-001.json")
        assert note.json_path == "/out/page-001.json"

    def test_synced_note_has_attempt_count(self):
        note = make_synced_note(attempt_count=0)
        assert note.attempt_count == 0

    def test_synced_note_has_synced_at(self):
        note = make_synced_note(synced_at=ANCHOR)
        assert note.synced_at == ANCHOR

    def test_svg_path_is_not_none_after_sync(self):
        note = make_synced_note()
        assert note.svg_path is not None


# ---------------------------------------------------------------------------
# Note entity — state-dependent fields (when clauses)
# ---------------------------------------------------------------------------

class TestNoteWhenFields:
    """Spec: when-qualified fields are absent outside their qualifying states."""

    # status = synced: all when-fields should be absent
    def test_synced_markdown_path_is_none(self):
        note = make_synced_note()
        assert note.markdown_path is None

    def test_synced_category_is_none(self):
        note = make_synced_note()
        assert note.category is None

    def test_synced_filename_is_none(self):
        note = make_synced_note()
        assert note.filename is None

    def test_synced_converted_at_is_none(self):
        note = make_synced_note()
        assert note.converted_at is None

    def test_synced_last_attempt_is_none(self):
        """last_attempt when status in (converting, converted, failed)."""
        note = make_synced_note()
        assert note.last_attempt is None

    # status = converting: last_attempt should be present
    def test_converting_last_attempt_is_set(self):
        note = make_converting_note()
        assert note.last_attempt is not None

    def test_converting_last_attempt_succeeded_is_false(self):
        note = make_converting_note()
        assert note.last_attempt.succeeded is False

    # status = converted: all when-fields should be present
    def test_converted_markdown_path_is_set(self):
        note = make_converted_note()
        assert note.markdown_path is not None

    def test_converted_category_is_set(self):
        note = make_converted_note()
        assert note.category is not None

    def test_converted_filename_is_set(self):
        note = make_converted_note()
        assert note.filename is not None

    def test_converted_at_is_set(self):
        note = make_converted_note()
        assert note.converted_at is not None

    def test_converted_last_attempt_is_set(self):
        note = make_converted_note()
        assert note.last_attempt is not None

    # status = failed: last_attempt present, converted fields absent
    def test_failed_last_attempt_is_set(self):
        note = make_failed_note()
        assert note.last_attempt is not None

    def test_failed_markdown_path_is_none(self):
        note = make_failed_note()
        assert note.markdown_path is None

    def test_failed_category_is_none(self):
        note = make_failed_note()
        assert note.category is None
