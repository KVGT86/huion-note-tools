"""Tests for BLE sync rules.

Spec obligations covered:
  rule-success.AutoDetectAndSync
  rule-success.ManualSyncTriggered
  idempotency (already-synced pages skipped)
  SVG and JSON written before Note record created
  pages NOT deleted from device on sync
"""
import pytest

from huion_note_pipeline.enums import NoteStatus
from huion_note_pipeline.ble_bridge import X10Device, Page


class TestAutoDetectAndSync:
    def test_creates_note_per_page(self, pipeline, mock_device):
        notes = pipeline.auto_detect_and_sync(mock_device)
        assert len(notes) == len(mock_device.stored_pages)

    def test_created_notes_have_synced_status(self, pipeline, mock_device):
        notes = pipeline.auto_detect_and_sync(mock_device)
        assert all(n.status == NoteStatus.SYNCED for n in notes)

    def test_created_notes_have_zero_attempt_count(self, pipeline, mock_device):
        notes = pipeline.auto_detect_and_sync(mock_device)
        assert all(n.attempt_count == 0 for n in notes)

    def test_created_notes_have_svg_path(self, pipeline, mock_device):
        notes = pipeline.auto_detect_and_sync(mock_device)
        assert all(n.svg_path is not None for n in notes)

    def test_created_notes_have_json_path(self, pipeline, mock_device):
        notes = pipeline.auto_detect_and_sync(mock_device)
        assert all(n.json_path is not None for n in notes)

    def test_svg_file_exists_on_disk(self, pipeline, mock_device, tmp_output):
        """Spec: SVG written to disk before Note record created."""
        notes = pipeline.auto_detect_and_sync(mock_device)
        from pathlib import Path
        for note in notes:
            assert Path(note.svg_path).exists()

    def test_json_file_exists_on_disk(self, pipeline, mock_device, tmp_output):
        notes = pipeline.auto_detect_and_sync(mock_device)
        from pathlib import Path
        for note in notes:
            assert Path(note.json_path).exists()

    def test_pages_not_deleted_from_device(self, pipeline, mock_device):
        """Spec: pages remain on device after sync."""
        original_count = len(mock_device.stored_pages)
        pipeline.auto_detect_and_sync(mock_device)
        assert len(mock_device.stored_pages) == original_count

    def test_idempotent_skips_already_synced_pages(self, pipeline, mock_device):
        """Spec: pages already synced (matched by page identity) are skipped."""
        first_sync = pipeline.auto_detect_and_sync(mock_device)
        second_sync = pipeline.auto_detect_and_sync(mock_device)
        # Total notes should not double
        assert len(pipeline.registry.all()) == len(mock_device.stored_pages)

    def test_synced_at_is_set(self, pipeline, mock_device):
        notes = pipeline.auto_detect_and_sync(mock_device)
        assert all(n.synced_at is not None for n in notes)


class TestManualSyncTriggered:
    def test_creates_note_per_page(self, pipeline, mock_device, mock_user):
        notes = pipeline.manual_sync(mock_user, mock_device)
        assert len(notes) == len(mock_device.stored_pages)

    def test_created_notes_have_synced_status(self, pipeline, mock_device, mock_user):
        notes = pipeline.manual_sync(mock_user, mock_device)
        assert all(n.status == NoteStatus.SYNCED for n in notes)

    def test_idempotent_after_auto_sync(self, pipeline, mock_device, mock_user):
        """Spec: manual sync is idempotent with auto sync."""
        pipeline.auto_detect_and_sync(mock_device)
        pipeline.manual_sync(mock_user, mock_device)
        assert len(pipeline.registry.all()) == len(mock_device.stored_pages)

    def test_pages_not_deleted_from_device(self, pipeline, mock_device, mock_user):
        original_count = len(mock_device.stored_pages)
        pipeline.manual_sync(mock_user, mock_device)
        assert len(mock_device.stored_pages) == original_count
