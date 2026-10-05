"""Filename collision handling tests.

Spec obligation: collision_index is None when filename is unique;
2, 3, ... when disambiguated within the same category folder.

Spec: 'If [ddmmyyyy]_[title].md already exists in the target folder,
collision_index increments from 2 upward until unique.'

Collision is scoped per-folder (work/, personal/, unclassified/ are independent).
"""
from pathlib import Path

import pytest

from huion_note_pipeline.enums import NoteCategory
from huion_note_pipeline.models import NoteFilename
from huion_note_pipeline.store import CollisionResolver
from tests.factories import ANCHOR, make_filename


# ---------------------------------------------------------------------------
# NoteFilename string representation
# ---------------------------------------------------------------------------

class TestNoteFilenameStringRepresentation:
    def test_no_collision_index_stem(self):
        fn = make_filename(date_part="21082026", title_part="bridge_calc", collision_index=None)
        assert str(fn) == "21082026_bridge_calc"

    def test_collision_index_2_stem(self):
        fn = make_filename(date_part="21082026", title_part="bridge_calc", collision_index=2)
        assert str(fn) == "21082026_bridge_calc_2"

    def test_collision_index_3_stem(self):
        fn = make_filename(date_part="21082026", title_part="bridge_calc", collision_index=3)
        assert str(fn) == "21082026_bridge_calc_3"

    def test_md_filename_no_index(self):
        fn = make_filename(date_part="21082026", title_part="site_visit", collision_index=None)
        assert fn.md_filename() == "21082026_site_visit.md"

    def test_md_filename_index_2(self):
        fn = make_filename(date_part="21082026", title_part="site_visit", collision_index=2)
        assert fn.md_filename() == "21082026_site_visit_2.md"

    def test_md_filename_index_3(self):
        fn = make_filename(date_part="21082026", title_part="site_visit", collision_index=3)
        assert fn.md_filename() == "21082026_site_visit_3.md"

    def test_svg_filename_no_index(self):
        fn = make_filename(date_part="21082026", title_part="sketch", collision_index=None)
        assert fn.svg_filename() == "21082026_sketch.svg"

    def test_svg_filename_index_2(self):
        fn = make_filename(date_part="21082026", title_part="sketch", collision_index=2)
        assert fn.svg_filename() == "21082026_sketch_2.svg"


# ---------------------------------------------------------------------------
# CollisionResolver: index_for
# ---------------------------------------------------------------------------

class TestCollisionResolverUniqueFilename:
    def test_returns_none_when_no_existing_file(self, collision_resolver, tmp_output):
        """No file exists → index_for returns None."""
        index = collision_resolver.index_for(
            synced_at=ANCHOR,
            title="fresh_note",
            category=NoteCategory.PERSONAL,
        )
        assert index is None

    def test_returns_none_for_different_title(self, collision_resolver, tmp_output):
        """A file with a different title does not cause collision."""
        (tmp_output / "personal" / "21082026_other_note.md").write_text("x")
        index = collision_resolver.index_for(
            synced_at=ANCHOR,
            title="fresh_note",
            category=NoteCategory.PERSONAL,
        )
        assert index is None

    def test_returns_none_for_different_date(self, collision_resolver, tmp_output):
        """A file with a different date does not cause collision."""
        (tmp_output / "personal" / "20082026_fresh_note.md").write_text("x")
        from datetime import datetime, timezone
        anchor_21 = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
        index = collision_resolver.index_for(
            synced_at=anchor_21,
            title="fresh_note",
            category=NoteCategory.PERSONAL,
        )
        assert index is None


class TestCollisionResolverSecondNote:
    def test_returns_2_when_base_filename_exists(self, collision_resolver, tmp_output):
        """Base file exists → index_for returns 2."""
        (tmp_output / "personal" / "21082026_site_visit.md").write_text("x")
        index = collision_resolver.index_for(
            synced_at=ANCHOR,
            title="site_visit",
            category=NoteCategory.PERSONAL,
        )
        assert index == 2

    def test_returns_3_when_base_and_2_exist(self, collision_resolver, tmp_output):
        """Base and _2 both exist → index_for returns 3."""
        (tmp_output / "personal" / "21082026_site_visit.md").write_text("x")
        (tmp_output / "personal" / "21082026_site_visit_2.md").write_text("x")
        index = collision_resolver.index_for(
            synced_at=ANCHOR,
            title="site_visit",
            category=NoteCategory.PERSONAL,
        )
        assert index == 3

    def test_increments_past_3(self, collision_resolver, tmp_output):
        """Works for arbitrarily deep collisions."""
        folder = tmp_output / "personal"
        (folder / "21082026_note.md").write_text("x")
        (folder / "21082026_note_2.md").write_text("x")
        (folder / "21082026_note_3.md").write_text("x")
        index = collision_resolver.index_for(
            synced_at=ANCHOR,
            title="note",
            category=NoteCategory.PERSONAL,
        )
        assert index == 4


class TestCollisionScopedPerFolder:
    """Collisions are per-folder. work/ and personal/ are independent."""

    def test_collision_in_work_does_not_affect_personal(self, collision_resolver, tmp_output):
        (tmp_output / "work" / "21082026_report.md").write_text("x")
        index = collision_resolver.index_for(
            synced_at=ANCHOR,
            title="report",
            category=NoteCategory.PERSONAL,
        )
        assert index is None

    def test_collision_in_personal_does_not_affect_work(self, collision_resolver, tmp_output):
        (tmp_output / "personal" / "21082026_report.md").write_text("x")
        index = collision_resolver.index_for(
            synced_at=ANCHOR,
            title="report",
            category=NoteCategory.WORK,
        )
        assert index is None

    def test_collision_in_personal_does_not_affect_unclassified(self, collision_resolver, tmp_output):
        (tmp_output / "personal" / "21082026_report.md").write_text("x")
        index = collision_resolver.index_for(
            synced_at=ANCHOR,
            title="report",
            category=NoteCategory.UNCLASSIFIED,
        )
        assert index is None

    def test_same_title_both_folders_independent_indices(self, collision_resolver, tmp_output):
        (tmp_output / "work" / "21082026_report.md").write_text("x")
        (tmp_output / "personal" / "21082026_report.md").write_text("x")
        (tmp_output / "personal" / "21082026_report_2.md").write_text("x")

        work_index = collision_resolver.index_for(
            synced_at=ANCHOR, title="report", category=NoteCategory.WORK
        )
        personal_index = collision_resolver.index_for(
            synced_at=ANCHOR, title="report", category=NoteCategory.PERSONAL
        )

        assert work_index == 2
        assert personal_index == 3
