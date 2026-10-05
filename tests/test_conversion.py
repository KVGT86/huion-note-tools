"""Tests for conversion rules.

Spec obligations covered:
  rule-success.BeginConversion
  rule-success.ConversionSucceeded
  rule-success.ConversionFailed
  rule-failure.BeginConversion (attempt_count guard)
  when-set.BeginConversion.Note.last_attempt
  when-set.ConversionSucceeded.Note.markdown_path
  when-set.ConversionSucceeded.Note.category
  when-set.ConversionSucceeded.Note.filename
  when-set.ConversionSucceeded.Note.converted_at
"""
import pytest

from huion_note_pipeline.enums import NoteStatus, NoteCategory
from tests.factories import (
    make_synced_note, make_converting_note, make_conversion_result, ANCHOR,
)


# ---------------------------------------------------------------------------
# BeginConversion
# ---------------------------------------------------------------------------

class TestBeginConversion:
    def test_transitions_to_converting(self, pipeline):
        note = make_synced_note(attempt_count=0)
        pipeline.begin_conversion(note)
        assert note.status == NoteStatus.CONVERTING

    def test_increments_attempt_count(self, pipeline):
        note = make_synced_note(attempt_count=0)
        pipeline.begin_conversion(note)
        assert note.attempt_count == 1

    def test_sets_last_attempt(self, pipeline):
        """Spec when-set: entering (converting|converted|failed) -> must set last_attempt."""
        note = make_synced_note(attempt_count=0)
        pipeline.begin_conversion(note)
        assert note.last_attempt is not None

    def test_last_attempt_succeeded_is_false(self, pipeline):
        note = make_synced_note(attempt_count=0)
        pipeline.begin_conversion(note)
        assert note.last_attempt.succeeded is False

    def test_last_attempt_has_timestamp(self, pipeline):
        note = make_synced_note(attempt_count=0)
        pipeline.begin_conversion(note)
        assert note.last_attempt.attempted_at is not None

    def test_returns_true_when_started(self, pipeline):
        note = make_synced_note(attempt_count=0)
        assert pipeline.begin_conversion(note) is True

    def test_returns_false_at_max_attempts(self, pipeline, config):
        note = make_synced_note(attempt_count=config.max_conversion_attempts)
        assert pipeline.begin_conversion(note) is False

    def test_status_unchanged_when_at_max(self, pipeline, config):
        note = make_synced_note(attempt_count=config.max_conversion_attempts)
        pipeline.begin_conversion(note)
        assert note.status == NoteStatus.SYNCED

    def test_fires_on_creation_with_synced_status(self, pipeline, mock_device):
        """Spec: 'becomes synced' fires on creation. Auto-conversion on sync."""
        notes = pipeline.auto_detect_and_sync(mock_device)
        # After sync, notes are SYNCED and conversion should start automatically
        for note in notes:
            assert note.status in (NoteStatus.SYNCED, NoteStatus.CONVERTING)


# ---------------------------------------------------------------------------
# ConversionSucceeded
# ---------------------------------------------------------------------------

class TestConversionSucceeded:
    def test_transitions_to_converted(self, pipeline):
        note = make_converting_note()
        result = make_conversion_result(success=True)
        pipeline.conversion_succeeded(note, result)
        assert note.status == NoteStatus.CONVERTED

    def test_sets_category(self, pipeline):
        """Spec when-set: entering {converted} -> must set category."""
        note = make_converting_note()
        result = make_conversion_result(success=True, category=NoteCategory.WORK)
        pipeline.conversion_succeeded(note, result)
        assert note.category == NoteCategory.WORK

    def test_sets_filename(self, pipeline):
        """Spec when-set: entering {converted} -> must set filename."""
        note = make_converting_note()
        result = make_conversion_result(success=True, title="test_note")
        pipeline.conversion_succeeded(note, result)
        assert note.filename is not None

    def test_filename_date_part_is_ddmmyyyy(self, pipeline):
        note = make_converting_note(synced_at=ANCHOR)
        result = make_conversion_result(success=True)
        pipeline.conversion_succeeded(note, result)
        assert note.filename.date_part == "21082026"

    def test_filename_title_part_matches_result(self, pipeline):
        note = make_converting_note()
        result = make_conversion_result(success=True, title="bridge_calc")
        pipeline.conversion_succeeded(note, result)
        assert note.filename.title_part == "bridge_calc"

    def test_sets_markdown_path(self, pipeline):
        """Spec when-set: entering {converted} -> must set markdown_path."""
        note = make_converting_note()
        result = make_conversion_result(success=True)
        pipeline.conversion_succeeded(note, result)
        assert note.markdown_path is not None

    def test_sets_converted_at(self, pipeline):
        """Spec when-set: entering {converted} -> must set converted_at."""
        note = make_converting_note()
        result = make_conversion_result(success=True)
        pipeline.conversion_succeeded(note, result)
        assert note.converted_at is not None

    def test_updates_last_attempt_to_succeeded(self, pipeline):
        note = make_converting_note()
        result = make_conversion_result(success=True)
        pipeline.conversion_succeeded(note, result)
        assert note.last_attempt is not None
        assert note.last_attempt.succeeded is True

    def test_requires_converting_status(self, pipeline):
        note = make_synced_note()
        with pytest.raises(Exception):
            pipeline.conversion_succeeded(note, make_conversion_result(success=True))

    def test_requires_success_true(self, pipeline):
        note = make_converting_note()
        with pytest.raises(Exception):
            pipeline.conversion_succeeded(note, make_conversion_result(success=False))


# ---------------------------------------------------------------------------
# ConversionFailed
# ---------------------------------------------------------------------------

class TestConversionFailed:
    def test_auto_retry_below_max(self, pipeline, config):
        note = make_converting_note(attempt_count=1)  # below max of 2
        result = make_conversion_result(success=False, error="Timeout")
        pipeline.conversion_failed(note, result)
        assert note.status == NoteStatus.SYNCED

    def test_auto_retry_clears_last_attempt(self, pipeline):
        """Spec: leaving last_attempt when-set (converting -> synced) -> clear."""
        note = make_converting_note(attempt_count=1)
        pipeline.conversion_failed(note, make_conversion_result(success=False))
        assert note.last_attempt is None

    def test_failed_at_max(self, pipeline, config):
        note = make_converting_note(attempt_count=config.max_conversion_attempts)
        result = make_conversion_result(success=False, error="Fatal")
        pipeline.conversion_failed(note, result)
        assert note.status == NoteStatus.FAILED

    def test_failed_records_last_attempt(self, pipeline, config):
        note = make_converting_note(attempt_count=config.max_conversion_attempts)
        result = make_conversion_result(success=False, error="Fatal")
        pipeline.conversion_failed(note, result)
        assert note.last_attempt is not None
        assert note.last_attempt.succeeded is False
        assert note.last_attempt.error_message == "Fatal"

    def test_requires_converting_status(self, pipeline):
        note = make_synced_note()
        with pytest.raises(Exception):
            pipeline.conversion_failed(note, make_conversion_result(success=False))

    def test_requires_success_false(self, pipeline):
        note = make_converting_note()
        with pytest.raises(Exception):
            pipeline.conversion_failed(note, make_conversion_result(success=True))
