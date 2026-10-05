"""YAML frontmatter schema validation tests.

Spec:
  Antigravity produces Obsidian-compatible YAML frontmatter with:
    title    - derived from note content
    date     - sync date
    category - NoteCategory value
    tags     - auto-inferred list from content

  Format:
    ---
    title: Bridge calculations
    date: 2026-08-21
    category: work
    tags:
      - engineering
    ---
"""
from typing import List, Optional

import pytest
import yaml

from huion_note_pipeline.enums import NoteCategory
from huion_note_pipeline.frontmatter import (
    build_frontmatter,
    render_frontmatter,
    parse_frontmatter,
    OBSIDIAN_FRONTMATTER_REQUIRED_KEYS,
)


# ---------------------------------------------------------------------------
# build_frontmatter: dict structure
# ---------------------------------------------------------------------------

class TestBuildFrontmatter:
    def test_returns_dict(self):
        fm = build_frontmatter(
            title="Bridge calculations",
            sync_date="2026-08-21",
            category=NoteCategory.WORK,
            tags=["engineering"],
        )
        assert isinstance(fm, dict)

    def test_has_title_key(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.PERSONAL)
        assert "title" in fm

    def test_has_date_key(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.PERSONAL)
        assert "date" in fm

    def test_has_category_key(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.PERSONAL)
        assert "category" in fm

    def test_has_tags_key(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.PERSONAL)
        assert "tags" in fm

    def test_title_value_matches_input(self):
        fm = build_frontmatter("Bridge calc", "2026-08-21", NoteCategory.WORK)
        assert fm["title"] == "Bridge calc"

    def test_date_value_matches_input(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.WORK)
        assert fm["date"] == "2026-08-21"

    def test_category_value_is_string_not_enum(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.WORK)
        assert fm["category"] == "work"
        assert isinstance(fm["category"], str)

    def test_category_work(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.WORK)
        assert fm["category"] == "work"

    def test_category_personal(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.PERSONAL)
        assert fm["category"] == "personal"

    def test_category_unclassified(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.UNCLASSIFIED)
        assert fm["category"] == "unclassified"

    def test_tags_is_list(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.WORK, tags=["a", "b"])
        assert isinstance(fm["tags"], list)

    def test_tags_values_preserved(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.WORK, tags=["engineering", "site"])
        assert "engineering" in fm["tags"]
        assert "site" in fm["tags"]

    def test_tags_defaults_to_empty_list(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.PERSONAL)
        assert fm["tags"] == []

    def test_has_all_required_keys(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.WORK)
        assert OBSIDIAN_FRONTMATTER_REQUIRED_KEYS.issubset(set(fm.keys()))

    def test_category_value_is_valid_enum_member(self):
        fm = build_frontmatter("Test", "2026-08-21", NoteCategory.WORK)
        assert fm["category"] in {c.value for c in NoteCategory}


# ---------------------------------------------------------------------------
# render_frontmatter: YAML fence format
# ---------------------------------------------------------------------------

class TestRenderFrontmatter:
    def _render(self, **kwargs):
        fm = build_frontmatter(**kwargs)
        return render_frontmatter(fm)

    def test_starts_with_triple_dashes(self):
        rendered = self._render(
            title="T", sync_date="2026-08-21", category=NoteCategory.PERSONAL
        )
        assert rendered.startswith("---\n")

    def test_ends_with_triple_dashes(self):
        rendered = self._render(
            title="T", sync_date="2026-08-21", category=NoteCategory.PERSONAL
        )
        assert rendered.strip().endswith("---")

    def test_is_valid_yaml_between_fences(self):
        rendered = self._render(
            title="Bridge calc",
            sync_date="2026-08-21",
            category=NoteCategory.WORK,
            tags=["engineering"],
        )
        inner = rendered.strip().strip("-").strip()
        parsed = yaml.safe_load(inner)
        assert isinstance(parsed, dict)

    def test_rendered_title_present(self):
        rendered = self._render(
            title="My Note", sync_date="2026-08-21", category=NoteCategory.PERSONAL
        )
        assert "My Note" in rendered

    def test_rendered_date_present(self):
        rendered = self._render(
            title="T", sync_date="2026-08-21", category=NoteCategory.PERSONAL
        )
        assert "2026-08-21" in rendered

    def test_rendered_category_present(self):
        rendered = self._render(
            title="T", sync_date="2026-08-21", category=NoteCategory.WORK
        )
        assert "work" in rendered

    def test_rendered_tags_present(self):
        rendered = self._render(
            title="T",
            sync_date="2026-08-21",
            category=NoteCategory.WORK,
            tags=["engineering"],
        )
        assert "engineering" in rendered


# ---------------------------------------------------------------------------
# parse_frontmatter: round-trip
# ---------------------------------------------------------------------------

class TestParseFrontmatter:
    def test_round_trip(self):
        fm = build_frontmatter(
            title="Bridge",
            sync_date="2026-08-21",
            category=NoteCategory.WORK,
            tags=["structural"],
        )
        rendered = render_frontmatter(fm)
        document = rendered + "\n## Notes\n\nSome content here.\n"
        parsed = parse_frontmatter(document)
        assert parsed is not None
        assert parsed["title"] == "Bridge"
        assert parsed["category"] == "work"
        assert parsed["tags"] == ["structural"]

    def test_returns_none_when_no_frontmatter(self):
        parsed = parse_frontmatter("## Hello\n\nNo frontmatter here.")
        assert parsed is None

    def test_parsed_tags_is_list(self):
        fm = build_frontmatter("T", "2026-08-21", NoteCategory.PERSONAL, tags=["a", "b"])
        doc = render_frontmatter(fm) + "\ncontent"
        parsed = parse_frontmatter(doc)
        assert isinstance(parsed["tags"], list)
