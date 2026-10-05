"""Category routing tests.

Spec:
  CYCLOPS marker present and legible  -> work      -> work/
  No CYCLOPS marker                   -> personal  -> personal/
  Marker ambiguous / unreadable       -> unclassified -> unclassified/

  SVG backup mirrors markdown path:
    work/[filename].md   and   work/[filename].svg
    personal/[...]       and   personal/[...]
    unclassified/[...]   and   unclassified/[...]
"""
from pathlib import Path

import pytest

from huion_note_pipeline.enums import NoteCategory
from huion_note_pipeline.store import category_folder
from tests.factories import (
    make_converting_note, make_conversion_result, make_filename, ANCHOR,
)


# ---------------------------------------------------------------------------
# CategoryFolder function
# ---------------------------------------------------------------------------

class TestCategoryFolder:
    def test_work_maps_to_work_folder(self, config, tmp_output):
        folder = category_folder(NoteCategory.WORK, config.output_directory)
        assert folder == tmp_output / "work"

    def test_personal_maps_to_personal_folder(self, config, tmp_output):
        folder = category_folder(NoteCategory.PERSONAL, config.output_directory)
        assert folder == tmp_output / "personal"

    def test_unclassified_maps_to_unclassified_folder(self, config, tmp_output):
        folder = category_folder(NoteCategory.UNCLASSIFIED, config.output_directory)
        assert folder == tmp_output / "unclassified"

    def test_folders_are_relative_to_output_directory(self, config, tmp_output):
        folder = category_folder(NoteCategory.WORK, config.output_directory)
        assert str(folder).startswith(str(tmp_output))


# ---------------------------------------------------------------------------
# Category routing through ConversionSucceeded
# ---------------------------------------------------------------------------

class TestCategoryRouting:
    def test_work_result_sets_note_category_to_work(self, pipeline):
        note = make_converting_note()
        result = make_conversion_result(success=True, category=NoteCategory.WORK)
        pipeline.conversion_succeeded(note, result)
        assert note.category == NoteCategory.WORK

    def test_personal_result_sets_note_category_to_personal(self, pipeline):
        note = make_converting_note()
        result = make_conversion_result(success=True, category=NoteCategory.PERSONAL)
        pipeline.conversion_succeeded(note, result)
        assert note.category == NoteCategory.PERSONAL

    def test_unclassified_result_sets_note_category_to_unclassified(self, pipeline):
        note = make_converting_note()
        result = make_conversion_result(success=True, category=NoteCategory.UNCLASSIFIED)
        pipeline.conversion_succeeded(note, result)
        assert note.category == NoteCategory.UNCLASSIFIED


# ---------------------------------------------------------------------------
# Markdown written to correct category folder
# ---------------------------------------------------------------------------

class TestMarkdownFolderRouting:
    def test_work_note_markdown_in_work_folder(self, pipeline, tmp_output):
        note = make_converting_note()
        result = make_conversion_result(success=True, category=NoteCategory.WORK)
        pipeline.conversion_succeeded(note, result)
        assert note.markdown_path is not None
        assert Path(note.markdown_path).parent == tmp_output / "work"

    def test_personal_note_markdown_in_personal_folder(self, pipeline, tmp_output):
        note = make_converting_note()
        result = make_conversion_result(success=True, category=NoteCategory.PERSONAL)
        pipeline.conversion_succeeded(note, result)
        assert Path(note.markdown_path).parent == tmp_output / "personal"

    def test_unclassified_note_markdown_in_unclassified_folder(self, pipeline, tmp_output):
        note = make_converting_note()
        result = make_conversion_result(success=True, category=NoteCategory.UNCLASSIFIED)
        pipeline.conversion_succeeded(note, result)
        assert Path(note.markdown_path).parent == tmp_output / "unclassified"


# ---------------------------------------------------------------------------
# SVG backup mirrors markdown path (spec: unclassified SVG mirrors markdown)
# ---------------------------------------------------------------------------

class TestSvgBackupLocation:
    def test_work_svg_backup_in_work_folder(self, pipeline, markdown_store, tmp_output):
        note = make_converting_note()
        result = make_conversion_result(success=True, category=NoteCategory.WORK)
        pipeline.conversion_succeeded(note, result)
        svg_backup = (
            tmp_output
            / "work"
            / note.filename.svg_filename()
        )
        assert svg_backup.exists()

    def test_personal_svg_backup_in_personal_folder(self, pipeline, tmp_output):
        note = make_converting_note()
        result = make_conversion_result(success=True, category=NoteCategory.PERSONAL)
        pipeline.conversion_succeeded(note, result)
        svg_backup = tmp_output / "personal" / note.filename.svg_filename()
        assert svg_backup.exists()

    def test_unclassified_svg_mirrors_markdown_path(self, pipeline, tmp_output):
        """Spec: unclassified SVGs mirror their markdown path exactly."""
        note = make_converting_note()
        result = make_conversion_result(success=True, category=NoteCategory.UNCLASSIFIED)
        pipeline.conversion_succeeded(note, result)
        svg_backup = tmp_output / "unclassified" / note.filename.svg_filename()
        assert svg_backup.exists()

    def test_svg_and_markdown_share_base_filename(self, pipeline):
        note = make_converting_note()
        result = make_conversion_result(success=True, category=NoteCategory.PERSONAL)
        pipeline.conversion_succeeded(note, result)
        md_stem = Path(note.markdown_path).stem
        svg_stem = Path(note.filename.svg_filename()).stem
        assert md_stem == svg_stem
