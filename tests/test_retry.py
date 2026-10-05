"""Retry logic tests.

Spec obligations covered:
  rule-success.UserRetriesNote
  when-clear.UserRetriesNote.Note.last_attempt
  rule-failure.UserRetriesNote (rejected when not failed)
  auto-retry once before failure state
  failure state after 2 attempts
  manual retry resets state (unlimited retries)

Spec rules:
  BeginConversion: requires attempt_count < config.max_conversion_attempts
  ConversionFailed:
    if attempt_count < max: status = synced (auto-retry), last_attempt = null
    else: status = failed
  UserRetriesNote:
    requires: status = failed
    ensures: status = synced, attempt_count = 0, last_attempt = null
"""
import pytest

from huion_note_pipeline.enums import NoteStatus
from tests.factories import (
    make_synced_note, make_converting_note, make_failed_note, make_conversion_result,
)


# ---------------------------------------------------------------------------
# Auto-retry: one automatic retry before failure state
# ---------------------------------------------------------------------------

class TestAutoRetryLogic:
    def test_first_failure_retries_automatically(self, pipeline, config):
        """Spec: if attempt_count < max -> status = synced (auto-retry)."""
        note = make_synced_note(attempt_count=0)
        pipeline.begin_conversion(note)       # attempt_count becomes 1
        result = make_conversion_result(success=False, error="Error")
        pipeline.conversion_failed(note, result)
        assert note.status == NoteStatus.SYNCED  # auto-retried

    def test_auto_retry_clears_last_attempt(self, pipeline):
        """Spec: leaving last_attempt when-set -> must clear last_attempt."""
        note = make_synced_note(attempt_count=0)
        pipeline.begin_conversion(note)
        result = make_conversion_result(success=False)
        pipeline.conversion_failed(note, result)
        assert note.last_attempt is None  # cleared per spec

    def test_second_failure_produces_failed_state(self, pipeline, config):
        """Spec: if attempt_count >= max -> status = failed."""
        note = make_synced_note(attempt_count=0)

        # First attempt + failure (auto-retry)
        pipeline.begin_conversion(note)   # attempt_count = 1
        pipeline.conversion_failed(note, make_conversion_result(success=False))
        assert note.status == NoteStatus.SYNCED

        # Second attempt + failure (max reached)
        pipeline.begin_conversion(note)   # attempt_count = 2 = max
        pipeline.conversion_failed(note, make_conversion_result(success=False, error="Fatal"))
        assert note.status == NoteStatus.FAILED

    def test_failed_state_retains_last_attempt_error(self, pipeline):
        note = make_synced_note(attempt_count=0)
        pipeline.begin_conversion(note)
        pipeline.conversion_failed(note, make_conversion_result(success=False))
        pipeline.begin_conversion(note)  # second attempt
        result = make_conversion_result(success=False, error="OCR failed")
        pipeline.conversion_failed(note, result)
        assert note.status == NoteStatus.FAILED
        assert note.last_attempt is not None
        assert note.last_attempt.error_message == "OCR failed"

    def test_auto_retry_does_not_fire_beyond_max(self, pipeline, config):
        """Spec: BeginConversion requires attempt_count < max."""
        note = make_synced_note(attempt_count=config.max_conversion_attempts)
        started = pipeline.begin_conversion(note)
        assert started is False
        assert note.status == NoteStatus.SYNCED


# ---------------------------------------------------------------------------
# Manual retry: UserRetriesNote
# ---------------------------------------------------------------------------

class TestManualRetry:
    def test_user_retries_failed_note_transitions_to_synced(self, pipeline, mock_user):
        """Spec: UserRetriesNote ensures status = synced."""
        note = make_failed_note()
        pipeline.user_retries_note(mock_user, note)
        assert note.status == NoteStatus.SYNCED

    def test_user_retries_resets_attempt_count_to_zero(self, pipeline, mock_user):
        """Spec: UserRetriesNote ensures attempt_count = 0."""
        note = make_failed_note(attempt_count=2)
        pipeline.user_retries_note(mock_user, note)
        assert note.attempt_count == 0

    def test_user_retries_clears_last_attempt(self, pipeline, mock_user):
        """Spec when-clear: UserRetriesNote must clear last_attempt (leaving when-set)."""
        note = make_failed_note()
        assert note.last_attempt is not None  # pre-condition
        pipeline.user_retries_note(mock_user, note)
        assert note.last_attempt is None

    def test_user_retries_rejected_when_not_failed(self, pipeline, mock_user):
        """Spec: UserRetriesNote requires status = failed."""
        note = make_synced_note()
        with pytest.raises(Exception):
            pipeline.user_retries_note(mock_user, note)

    def test_user_retries_rejected_when_converting(self, pipeline, mock_user):
        note = make_converting_note()
        with pytest.raises(Exception):
            pipeline.user_retries_note(mock_user, note)

    def test_user_retries_rejected_when_converted(self, pipeline, mock_user):
        from tests.factories import make_converted_note
        note = make_converted_note()
        with pytest.raises(Exception):
            pipeline.user_retries_note(mock_user, note)


# ---------------------------------------------------------------------------
# Unlimited manual retries
# ---------------------------------------------------------------------------

class TestUnlimitedManualRetries:
    """Spec: manual retries are unlimited. attempt_count = 0 reset allows fresh cycles."""

    def test_can_retry_after_second_failure(self, pipeline, config, mock_user):
        note = make_failed_note(attempt_count=config.max_conversion_attempts)
        pipeline.user_retries_note(mock_user, note)
        assert note.status == NoteStatus.SYNCED
        assert note.attempt_count == 0

    def test_can_retry_multiple_times(self, pipeline, config, mock_user):
        """User can retry indefinitely; each cycle gives fresh auto-retry window."""
        note = make_synced_note()
        for cycle in range(3):  # 3 manual retry cycles
            # Exhaust auto-retries
            for _ in range(config.max_conversion_attempts):
                pipeline.begin_conversion(note)
                pipeline.conversion_failed(note, make_conversion_result(success=False))
            assert note.status == NoteStatus.FAILED
            # Manual retry resets
            pipeline.user_retries_note(mock_user, note)
            assert note.status == NoteStatus.SYNCED
            assert note.attempt_count == 0

    def test_retry_enables_fresh_auto_retry_cycle(self, pipeline, config, mock_user):
        """After manual retry, full auto-retry window is available again."""
        note = make_failed_note(attempt_count=config.max_conversion_attempts)
        pipeline.user_retries_note(mock_user, note)

        # First attempt (count will become 1)
        started = pipeline.begin_conversion(note)
        assert started is True
        assert note.attempt_count == 1

        # One more auto-retry should still be available
        pipeline.conversion_failed(note, make_conversion_result(success=False))
        assert note.status == NoteStatus.SYNCED  # auto-retried, not failed
