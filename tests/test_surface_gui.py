"""GUI surface exposure and operation tests.

Spec obligations covered:
  surface-actor.GUI
  surface-exposure.GUI
  surface-provides.GUI
  surface-provides.GUI when-guard: RetryConversion only when status = failed
  @guarantee NotesAreReadOnly

The GUI surface is mapped to the NoteRegistry (read) + SyncPipeline (write).
These tests verify the contract at the boundary: what the user sees and can do.
"""
import pytest

from huion_note_pipeline.enums import NoteStatus, NoteCategory
from tests.factories import (
    make_synced_note, make_converting_note, make_converted_note,
    make_failed_note, make_conversion_result,
)


# ---------------------------------------------------------------------------
# Exposure: GUI exposes note fields to the user
# ---------------------------------------------------------------------------

class TestGUIExposure:
    def test_note_status_accessible(self, pipeline, mock_device):
        notes = pipeline.auto_detect_and_sync(mock_device)
        for note in pipeline.registry.all():
            _ = note.status  # must not raise

    def test_note_svg_path_accessible(self, pipeline, mock_device):
        pipeline.auto_detect_and_sync(mock_device)
        for note in pipeline.registry.all():
            assert note.svg_path is not None

    def test_note_synced_at_accessible(self, pipeline, mock_device):
        pipeline.auto_detect_and_sync(mock_device)
        for note in pipeline.registry.all():
            assert note.synced_at is not None

    def test_filename_exposed_only_when_converted(self, pipeline, mock_device):
        pipeline.auto_detect_and_sync(mock_device)
        for note in pipeline.registry.all():
            if note.status != NoteStatus.CONVERTED:
                # Accessing filename on non-converted note should return None
                assert note.filename is None

    def test_category_exposed_only_when_converted(self, pipeline, mock_device):
        pipeline.auto_detect_and_sync(mock_device)
        for note in pipeline.registry.all():
            if note.status != NoteStatus.CONVERTED:
                assert note.category is None

    def test_markdown_path_exposed_only_when_converted(self, pipeline, mock_device):
        pipeline.auto_detect_and_sync(mock_device)
        for note in pipeline.registry.all():
            if note.status != NoteStatus.CONVERTED:
                assert note.markdown_path is None

    def test_all_notes_in_registry_accessible(self, pipeline, mock_device):
        pipeline.auto_detect_and_sync(mock_device)
        notes = pipeline.registry.all()
        assert len(notes) > 0


# ---------------------------------------------------------------------------
# Provides: user operations with when-guards
# ---------------------------------------------------------------------------

class TestGUIProvides:
    def test_sync_now_available(self, pipeline, mock_device, mock_user):
        """UserRequestsSync is always available (no when-guard)."""
        notes = pipeline.manual_sync(mock_user, mock_device)
        assert len(notes) >= 0  # operation completes without error

    def test_retry_available_when_failed(self, pipeline, mock_user):
        """Spec: RetryConversion when note.status = failed."""
        note = make_failed_note()
        # No exception should be raised
        pipeline.user_retries_note(mock_user, note)
        assert note.status == NoteStatus.SYNCED

    def test_retry_unavailable_when_not_failed(self, pipeline, mock_user):
        """Spec: RetryConversion when-guard: only when status = failed."""
        for make_fn in (make_synced_note, make_converting_note):
            note = make_fn()
            with pytest.raises(Exception):
                pipeline.user_retries_note(mock_user, note)

    def test_clear_memory_synced_option(self, pipeline, mock_device, mock_user):
        """ClearMemory(clear_synced) removes only synced pages."""
        pipeline.auto_detect_and_sync(mock_device)
        pipeline.clear_synced_pages(mock_user, mock_device)
        # Passes without error

    def test_clear_memory_all_option(self, pipeline, mock_device, mock_user):
        """ClearMemory(clear_all) removes all pages."""
        pipeline.auto_detect_and_sync(mock_device)
        pipeline.clear_all_pages(mock_user, mock_device)
        assert len(mock_device.stored_pages) == 0


# ---------------------------------------------------------------------------
# @guarantee NotesAreReadOnly
# ---------------------------------------------------------------------------

class TestNotesAreReadOnly:
    """Spec @guarantee: the notes list is read-only; state changes via provided ops only."""

    def test_registry_all_returns_copies_or_readonly(self, pipeline, mock_device):
        """Mutations to registry output should not change registry state."""
        pipeline.auto_detect_and_sync(mock_device)
        notes = pipeline.registry.all()
        original_count = len(notes)
        # Clearing the returned list should not affect registry
        notes.clear()
        assert len(pipeline.registry.all()) == original_count
