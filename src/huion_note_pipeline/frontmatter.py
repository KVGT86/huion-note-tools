"""Obsidian-compatible YAML frontmatter generation.

Spec: Antigravity produces Obsidian YAML frontmatter:
  title    - derived from content by Antigravity
  date     - sync date
  category - NoteCategory (work | personal | unclassified)
  tags     - auto-inferred from content by Antigravity

Format (Obsidian standard):
  ---
  title: Bridge calculations
  date: 2026-08-21
  category: work
  tags:
    - engineering
    - structural
  ---
"""
from __future__ import annotations

from typing import List, Optional

import yaml

from .enums import NoteCategory
from .models import NoteFilename


OBSIDIAN_FRONTMATTER_REQUIRED_KEYS = {"title", "date", "category", "tags"}


def build_frontmatter(
    title: str,
    sync_date: str,
    category: NoteCategory,
    tags: Optional[List[str]] = None,
) -> dict:
    """Build a frontmatter dict suitable for Obsidian.

    date is expected in YYYY-MM-DD format (Obsidian standard).
    tags is a list of strings; defaults to empty list.
    """
    category_val = category.value if isinstance(category, NoteCategory) else str(category)
    return {
        "title": title,
        "date": sync_date,
        "category": category_val,
        "tags": list(tags) if tags is not None else [],
    }


def render_frontmatter(frontmatter: dict) -> str:
    """Render a frontmatter dict as a YAML-fenced block.

    Returns a string beginning with '---\n' and ending with '---\n'.
    """
    yaml_content = yaml.dump(
        frontmatter,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    return f"---\n{yaml_content}---\n"


def parse_frontmatter(markdown: str) -> Optional[dict]:
    """Extract and parse frontmatter from a markdown string.

    Returns None if no frontmatter block is present.
    Returns the parsed dict otherwise.
    """
    if not markdown.startswith("---"):
        return None
    parts = markdown.split("---", 2)
    if len(parts) < 3:
        return None
    fm_text = parts[1].strip()
    if not fm_text:
        return None
    try:
        parsed = yaml.safe_load(fm_text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None
