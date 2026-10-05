"""Tests for NoteCategory and NoteStatus enumerations.

Spec obligations covered:
  enum-comparable.NoteCategory
  enum-comparable.NoteStatus
"""
import pytest

from huion_note_pipeline.enums import NoteCategory, NoteStatus


class TestNoteCategory:
    def test_has_work_value(self):
        assert NoteCategory.WORK == "work"

    def test_has_personal_value(self):
        assert NoteCategory.PERSONAL == "personal"

    def test_has_unclassified_value(self):
        assert NoteCategory.UNCLASSIFIED == "unclassified"

    def test_all_three_values_exist(self):
        values = {c.value for c in NoteCategory}
        assert values == {"work", "personal", "unclassified"}

    def test_comparable_equal(self):
        assert NoteCategory.WORK == NoteCategory.WORK

    def test_comparable_not_equal(self):
        assert NoteCategory.WORK != NoteCategory.PERSONAL

    def test_comparable_with_string(self):
        assert NoteCategory.WORK == "work"

    def test_membership(self):
        assert NoteCategory.WORK in NoteCategory


class TestNoteStatus:
    def test_has_synced_value(self):
        assert NoteStatus.SYNCED == "synced"

    def test_has_converting_value(self):
        assert NoteStatus.CONVERTING == "converting"

    def test_has_converted_value(self):
        assert NoteStatus.CONVERTED == "converted"

    def test_has_failed_value(self):
        assert NoteStatus.FAILED == "failed"

    def test_all_four_values_exist(self):
        values = {s.value for s in NoteStatus}
        assert values == {"synced", "converting", "converted", "failed"}

    def test_comparable_equal(self):
        assert NoteStatus.SYNCED == NoteStatus.SYNCED

    def test_comparable_not_equal(self):
        assert NoteStatus.SYNCED != NoteStatus.CONVERTED

    def test_comparable_with_string(self):
        assert NoteStatus.CONVERTING == "converting"
