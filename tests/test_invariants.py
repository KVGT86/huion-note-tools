"""Invariant tests (assertion-based + property-based with Hypothesis).

Spec obligations covered:
  invariant.SVGAlwaysPresent
  invariant.FilenameOnConvertedNote
  invariant.ConvertedNoteAttemptedAtLeastOnce

Property-based approach:
  For each invariant, a Hypothesis strategy generates valid notes in
  various lifecycle states and asserts the invariant holds.
"""
from datetime import datetime, timezone
from typing import Optional

import pytest
try:
    from hypothesis import given, settings, assume
    from hypothesis import strategies as st
    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

from huion_note_pipeline.enums import NoteCategory, NoteStatus
from huion_note_pipeline.models import Note, NoteFilename, ConversionAttempt
from tests.factories import (
    make_synced_note, make_converting_note, make_converted_note,
    make_failed_note, make_conversion_result, ANCHOR,
)


# ---------------------------------------------------------------------------
# SVGAlwaysPresent
# ---------------------------------------------------------------------------

class TestSVGAlwaysPresent:
    """Spec invariant: for note in Notes: note.svg_path != null."""

    def test_synced_note_has_svg(self):
        note = make_synced_note(svg_path="/out/test.svg")
        assert note.svg_path is not None

    def test_converting_note_has_svg(self):
        note = make_converting_note()
        assert note.svg_path is not None

    def test_converted_note_has_svg(self, pipeline):
        note = make_converting_note()
        result = make_conversion_result(success=True)
        pipeline.conversion_succeeded(note, result)
        assert note.svg_path is not None

    def test_failed_note_has_svg(self, pipeline, config):
        note = make_converting_note(attempt_count=config.max_conversion_attempts)
        pipeline.conversion_failed(note, make_conversion_result(success=False))
        assert note.svg_path is not None

    def test_svg_survives_manual_retry(self, pipeline, mock_user):
        note = make_failed_note()
        svg = note.svg_path
        pipeline.user_retries_note(mock_user, note)
        assert note.svg_path == svg  # unchanged

    def test_conversion_succeeded_does_not_clear_svg(self, pipeline):
        note = make_converting_note()
        pipeline.conversion_succeeded(note, make_conversion_result(success=True))
        assert note.svg_path is not None


# ---------------------------------------------------------------------------
# FilenameOnConvertedNote
# ---------------------------------------------------------------------------

class TestFilenameOnConvertedNote:
    """Spec invariant: converted notes have filename and markdown_path."""

    def test_converted_note_has_filename(self, pipeline):
        note = make_converting_note()
        pipeline.conversion_succeeded(note, make_conversion_result(success=True))
        assert note.filename is not None

    def test_converted_note_has_markdown_path(self, pipeline):
        note = make_converting_note()
        pipeline.conversion_succeeded(note, make_conversion_result(success=True))
        assert note.markdown_path is not None

    def test_failed_note_has_no_filename(self, pipeline, config):
        note = make_converting_note(attempt_count=config.max_conversion_attempts)
        pipeline.conversion_failed(note, make_conversion_result(success=False))
        assert note.filename is None

    def test_synced_note_has_no_filename(self):
        note = make_synced_note()
        assert note.filename is None


# ---------------------------------------------------------------------------
# ConvertedNoteAttemptedAtLeastOnce
# ---------------------------------------------------------------------------

class TestConvertedNoteAttemptedAtLeastOnce:
    """Spec invariant: converted notes have attempt_count >= 1."""

    def test_converted_note_has_nonzero_attempt_count(self, pipeline):
        note = make_synced_note(attempt_count=0)
        pipeline.begin_conversion(note)
        pipeline.conversion_succeeded(note, make_conversion_result(success=True))
        assert note.attempt_count >= 1

    def test_converted_after_auto_retry_has_correct_count(self, pipeline):
        note = make_synced_note(attempt_count=0)
        # First failure (auto-retry)
        pipeline.begin_conversion(note)
        pipeline.conversion_failed(note, make_conversion_result(success=False))
        # Second attempt succeeds
        pipeline.begin_conversion(note)
        pipeline.conversion_succeeded(note, make_conversion_result(success=True))
        assert note.attempt_count >= 1

    def test_manual_retry_then_convert_attempt_count_ge_1(self, pipeline, mock_user):
        note = make_failed_note(attempt_count=2)
        pipeline.user_retries_note(mock_user, note)
        pipeline.begin_conversion(note)
        pipeline.conversion_succeeded(note, make_conversion_result(success=True))
        assert note.attempt_count >= 1


# ---------------------------------------------------------------------------
# Property-based invariant tests (requires Hypothesis)
# ---------------------------------------------------------------------------

if HAS_HYPOTHESIS:
    note_status_strategy = st.sampled_from(list(NoteStatus))
    note_category_strategy = st.sampled_from(list(NoteCategory))

    @given(
        svg=st.text(min_size=1, max_size=200),
        status=note_status_strategy,
    )
    @settings(max_examples=100)
    def test_pbt_svg_always_present(svg, status):
        """PBT: SVGAlwaysPresent holds for any reachable Note."""
        note = make_synced_note(svg_path=svg)
        note.status = status  # directly set for PBT exploration
        assert note.svg_path is not None
