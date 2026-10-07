"""Device memory management tests.

Spec obligations covered:
  rule-success.ClearSyncedPages
  rule-success.ClearAllPages
"""
import pytest
from pathlib import Path

from huion_note_pipeline.ble_bridge import X10Device, Page
from huion.models import ExportArtifacts
from huion.sync_engine import verify_export_artifacts


def test_export_verification_requires_every_declared_file(tmp_path):
    (tmp_path / "page.svg").write_text("<svg/>")
    artifacts = ExportArtifacts(str(tmp_path), svg_filename="page.svg", json_filename="page.json")
    assert not verify_export_artifacts(artifacts)
    (tmp_path / "page.json").write_text("{}")
    assert verify_export_artifacts(artifacts)


class TestClearSyncedPages:
    def test_removes_synced_pages_from_device(self, pipeline, mock_device, mock_user):
        """Spec: pages with a Note record are removed from device."""
        pipeline.auto_detect_and_sync(mock_device)
        original_count = len(mock_device.stored_pages)
        pipeline.clear_synced_pages(mock_user, mock_device)
        # All pages were synced, so all should be removed
        assert len(mock_device.stored_pages) == 0

    def test_retains_unsynced_pages(self, pipeline, mock_device, mock_user):
        """Spec: pages without a Note record are NOT removed."""
        # Only sync the first page
        partial_device = X10Device(address=mock_device.address)
        partial_device.stored_pages = [mock_device.stored_pages[0]]
        pipeline.auto_detect_and_sync(partial_device)

        # Now device has a new page added that was never synced
        mock_device.stored_pages.append(Page(page_id="unsynced-page"))
        pipeline.clear_synced_pages(mock_user, mock_device)

        # Only the unsynced page should remain
        remaining_ids = {p.page_id for p in mock_device.stored_pages}
        assert "unsynced-page" in remaining_ids

    def test_does_not_clear_unsynced_pages(self, pipeline, mock_user):
        """A device with no synced pages should not be emptied."""
        device = X10Device(address="FF:FF:FF:FF:FF:FF")
        device.stored_pages = [Page(page_id="not-synced")]
        pipeline.clear_synced_pages(mock_user, device)
        assert len(device.stored_pages) == 1


class TestClearAllPages:
    def test_removes_all_pages_from_device(self, pipeline, mock_device, mock_user):
        """Spec: all pages removed regardless of sync status."""
        pipeline.auto_detect_and_sync(mock_device)
        pipeline.clear_all_pages(mock_user, mock_device)
        assert len(mock_device.stored_pages) == 0

    def test_removes_unsynced_pages_too(self, pipeline, mock_user):
        device = X10Device(address="AA:BB:CC:DD:EE:FF")
        device.stored_pages = [Page(page_id="unsynced")]
        pipeline.clear_all_pages(mock_user, device)
        assert len(device.stored_pages) == 0

    def test_empty_device_stays_empty(self, pipeline, mock_user):
        device = X10Device(address="AA:BB:CC:DD:EE:FF")
        device.stored_pages = []
        pipeline.clear_all_pages(mock_user, device)
        assert len(device.stored_pages) == 0
