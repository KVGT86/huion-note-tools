"""Domain model derived from the Allium spec.

Spec source: huion-note-pipeline.allium
  entity Note { ... }
  value  NoteFilename { ... }
  value  ConversionAttempt { ... }
  value  ConversionResult { ... }
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

from .enums import NoteCategory, NoteStatus


# ---------------------------------------------------------------------------
# Value types (structural equality, no identity)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NoteFilename:
    """Spec: value NoteFilename.

    Pattern: [ddmmyyyy]_[context_title]
    Collision: [ddmmyyyy]_[context_title]_2, _3, ...
    """
    date_part: str            # ddmmyyyy of sync date
    title_part: str           # short title derived by Antigravity
    collision_index: Optional[int] = None  # None = unique; 2, 3, ... = disambiguated

    def __str__(self) -> str:
        """Return the base filename stem (no extension)."""
        if self.collision_index is not None and self.collision_index >= 2:
            return f"{self.date_part}_{self.title_part}_{self.collision_index}"
        return f"{self.date_part}_{self.title_part}"

    def md_filename(self) -> str:
        """Return the markdown filename including extension."""
        return f"{self}.md"

    def svg_filename(self) -> str:
        """Return the SVG filename including extension."""
        return f"{self}.svg"


@dataclass(frozen=True)
class ConversionAttempt:
    """Spec: value ConversionAttempt."""
    attempted_at: datetime
    succeeded: bool
    error_message: Optional[str] = None


@dataclass(frozen=True)
class ConversionResult:
    """Spec: value ConversionResult.

    Produced by Antigravity.convert(). Inputs to ConversionSucceeded /
    ConversionFailed rules.
    """
    success: bool
    derived_title: Optional[str] = None
    category: Optional[NoteCategory] = None
    markdown: Optional[str] = None
    tags: Optional[List[str]] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

@dataclass
class Note:
    """Spec: entity Note — a single page pulled from the X10 device.

    State-dependent fields:
      markdown_path, category, filename, converted_at
        → present only when status = converted
      last_attempt
        → present only when status in (converting, converted, failed)

    Invariants:
      SVGAlwaysPresent:              svg_path is never None
      FilenameOnConvertedNote:       converted note has filename and markdown_path
      ConvertedNoteAttemptedOnce:    converted note has attempt_count >= 1
    """
    svg_path: str
    json_path: str
    synced_at: datetime
    attempt_count: int = 0
    status: NoteStatus = NoteStatus.SYNCED

    # when status = converted
    markdown_path: Optional[str] = None
    category: Optional[NoteCategory] = None
    filename: Optional[NoteFilename] = None
    converted_at: Optional[datetime] = None

    # when status in (converting, converted, failed)
    last_attempt: Optional[ConversionAttempt] = None
