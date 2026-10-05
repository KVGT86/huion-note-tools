"""Transition graph tests for Note.status.

Spec obligations covered:
  transition-edge.Note.synced.converting
  transition-edge.Note.converting.converted
  transition-edge.Note.converting.failed
  transition-edge.Note.converting.synced
  transition-edge.Note.failed.synced
  transition-terminal.Note.converted
  reachability (happy path, auto-retry path, manual retry path)
  undeclared transitions rejected

Transition graph (from spec):
  synced      -> converting   (BeginConversion)
  converting  -> converted    (ConversionSucceeded)
  converting  -> failed       (ConversionFailed, max attempts)
  converting  -> synced       (ConversionFailed, auto-retry)
  failed      -> synced       (UserRetriesNote)
  terminal:   converted
"""
import pytest

from huion_note_pipeline.enums import NoteStatus
from huion_note_pipeline.models import ConversionResult
from tests.factories import (
    make_synced_note, make_converting_note, make_converted_note,
    make_failed_note, make_conversion_result,
)


# ---------------------------------------------------------------------------
# Individual edge reachability (witnessing rule: BeginConversion)
# ---------------------------------------------------------------------------

class TestTransitionSyncedToConverting:
    """Spec edge: synced -> converting. Witnessed by BeginConversion."""

    def test_begin_conversion_transitions_synced_to_converting(self, pipeline, mock_user):
        note = make_synced_note(attempt_count=0)
        started = pipeline.begin_conversion(note)
        assert started is True
        assert note.status == NoteStatus.CONVERTING

    def test_begin_conversion_rejected_at_max_attempts(self, pipeline):
        """Spec requires: attempt_count < config.max_conversion_attempts."""
        note = make_synced_note(attempt_count=2)  # default max is 2
        started = pipeline.begin_conversion(note)
        assert started is False
        assert note.status == NoteStatus.SYNCED


# ---------------------------------------------------------------------------
# Individual edge reachability (witnessing rule: ConversionSucceeded)
# ---------------------------------------------------------------------------

class TestTransitionConvertingToConverted:
    """Spec edge: converting -> converted. Witnessed by ConversionSucceeded."""

    def test_conversion_succeeded_transitions_to_converted(self, pipeline):
        note = make_converting_note()
        result = make_conversion_result(success=True)
        pipeline.conversion_succeeded(note, result)
        assert note.status == NoteStatus.CONVERTED


# ---------------------------------------------------------------------------
# Individual edge reachability (witnessing rule: ConversionFailed, max attempts)
# ---------------------------------------------------------------------------

class TestTransitionConvertingToFailed:
    """Spec edge: converting -> failed. Witnessed by ConversionFailed (at max)."""

    def test_conversion_failed_at_max_transitions_to_failed(self, pipeline, config):
        note = make_converting_note(attempt_count=config.max_conversion_attempts)
        result = make_conversion_result(success=False, error="Timeout")
        pipeline.conversion_failed(note, result)
        assert note.status == NoteStatus.FAILED


# ---------------------------------------------------------------------------
# Individual edge reachability (witnessing rule: ConversionFailed, auto-retry)
# ---------------------------------------------------------------------------

class TestTransitionConvertingToSynced:
    """Spec edge: converting -> synced. Witnessed by ConversionFailed (below max)."""

    def test_conversion_failed_below_max_transitions_to_synced(self, pipeline, config):
        note = make_converting_note(attempt_count=1)  # below max of 2
        result = make_conversion_result(success=False, error="Timeout")
        pipeline.conversion_failed(note, result)
        assert note.status == NoteStatus.SYNCED


# ---------------------------------------------------------------------------
# Individual edge reachability (witnessing rule: UserRetriesNote)
# ---------------------------------------------------------------------------

class TestTransitionFailedToSynced:
    """Spec edge: failed -> synced. Witnessed by UserRetriesNote."""

    def test_user_retries_failed_note_transitions_to_synced(self, pipeline, mock_user):
        note = make_failed_note()
        pipeline.user_retries_note(mock_user, note)
        assert note.status == NoteStatus.SYNCED


# ---------------------------------------------------------------------------
# Terminal state: converted has no automatic outbound transitions
# ---------------------------------------------------------------------------

class TestTerminalStateConverted:
    """Spec terminal: converted. No automatic rule progresses it further."""

    def test_begin_conversion_does_not_fire_on_converted_note(self, pipeline):
        note = make_converted_note()
        # begin_conversion should not alter a converted note
        started = pipeline.begin_conversion(note)
        assert started is False
        assert note.status == NoteStatus.CONVERTED


# ---------------------------------------------------------------------------
# Undeclared transitions must be rejected
# ---------------------------------------------------------------------------

class TestUndeclaredTransitions:
    """No undeclared edges in the transition graph should be reachable."""

    def test_synced_to_failed_is_not_reachable_directly(self, pipeline):
        """synced -> failed is not in the graph. Must go via converting."""
        note = make_synced_note()
        with pytest.raises(Exception):
            pipeline._transition_to_failed_directly(note)

    def test_synced_to_converted_is_not_reachable_directly(self, pipeline):
        """synced -> converted is not in the graph."""
        note = make_synced_note()
        with pytest.raises(Exception):
            pipeline._transition_to_converted_directly(note)

    def test_failed_to_converting_is_not_reachable_directly(self, pipeline, mock_user):
        """failed -> converting is not in the graph (must go via synced)."""
        note = make_failed_note()
        with pytest.raises(Exception):
            pipeline._transition_failed_to_converting(note)


# ---------------------------------------------------------------------------
# Reachability tests: full lifecycle paths
# ---------------------------------------------------------------------------

class TestReachabilityHappyPath:
    """Full path: synced -> converting -> converted."""

    def test_happy_path_lifecycle(self, pipeline, mock_user):
        note = make_synced_note(attempt_count=0)

        # synced -> converting
        started = pipeline.begin_conversion(note)
        assert started is True
        assert note.status == NoteStatus.CONVERTING

        # converting -> converted
        result = make_conversion_result(success=True)
        pipeline.conversion_succeeded(note, result)
        assert note.status == NoteStatus.CONVERTED
        assert note.filename is not None
        assert note.markdown_path is not None
        assert note.category is not None
        assert note.converted_at is not None


class TestReachabilityAutoRetryPath:
    """Path: synced -> converting -> (fail) -> synced -> converting -> converted."""

    def test_auto_retry_path_lifecycle(self, pipeline, config):
        note = make_synced_note(attempt_count=0)

        # First attempt
        pipeline.begin_conversion(note)
        assert note.status == NoteStatus.CONVERTING
        assert note.attempt_count == 1

        # First failure (below max) -> auto-retry back to synced
        result_fail = make_conversion_result(success=False, error="Error")
        pipeline.conversion_failed(note, result_fail)
        assert note.status == NoteStatus.SYNCED
        assert note.last_attempt is None  # cleared on exit from when-set

        # Second attempt (auto-triggered by synced status)
        pipeline.begin_conversion(note)
        assert note.status == NoteStatus.CONVERTING
        assert note.attempt_count == 2

        # Second attempt succeeds
        result_ok = make_conversion_result(success=True)
        pipeline.conversion_succeeded(note, result_ok)
        assert note.status == NoteStatus.CONVERTED


class TestReachabilityManualRetryPath:
    """Path: synced -> converting -> failed (x2) -> synced -> converting -> converted."""

    def test_manual_retry_path_lifecycle(self, pipeline, config, mock_user):
        note = make_synced_note(attempt_count=0)

        # Exhaust auto-retries: 2 failures
        for _ in range(config.max_conversion_attempts):
            pipeline.begin_conversion(note)
            result_fail = make_conversion_result(success=False, error="Error")
            pipeline.conversion_failed(note, result_fail)

        assert note.status == NoteStatus.FAILED

        # Manual retry resets state
        pipeline.user_retries_note(mock_user, note)
        assert note.status == NoteStatus.SYNCED
        assert note.attempt_count == 0
        assert note.last_attempt is None

        # Fresh conversion cycle
        pipeline.begin_conversion(note)
        result_ok = make_conversion_result(success=True)
        pipeline.conversion_succeeded(note, result_ok)
        assert note.status == NoteStatus.CONVERTED
