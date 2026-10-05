"""Enumerations derived from the Allium spec.

Spec source: huion-note-pipeline.allium
  enum NoteCategory { work | personal | unclassified }
  enum NoteStatus   { synced | converting | converted | failed }
"""
from enum import Enum


class NoteCategory(str, Enum):
    """Routing category for a converted note."""
    WORK = "work"
    PERSONAL = "personal"
    UNCLASSIFIED = "unclassified"


class NoteStatus(str, Enum):
    """Lifecycle state of a Note entity.

    Transition graph (spec §Note.status):
      synced      -> converting
      converting  -> converted    # ConversionSucceeded
      converting  -> failed       # ConversionFailed (max attempts reached)
      converting  -> synced       # ConversionFailed (auto-retry)
      failed      -> synced       # UserRetriesNote (manual retry)
      terminal:   converted
    """
    SYNCED = "synced"
    CONVERTING = "converting"
    CONVERTED = "converted"
    FAILED = "failed"
