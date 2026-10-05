"""Shared pytest fixtures for the Huion Note Pipeline test suite.

Fixture design:
  - Provides a temp output directory for each test.
  - Provides a PipelineConfig wired to the temp dir.
  - Provides mock X10Device and Page objects.
  - Provides a SyncPipeline wired with in-memory stores.
  - Time is injected via datetime overrides on factories.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from huion_note_pipeline.config import PipelineConfig
from huion_note_pipeline.pipeline import NoteRegistry, SyncPipeline
from huion_note_pipeline.store import SvgStore, JsonStore, MarkdownStore, CollisionResolver
from huion_note_pipeline.ble_bridge import X10Device, Page


ANCHOR_TIME = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    """A temporary output directory tree with work/, personal/, unclassified/ sub-dirs."""
    for sub in ("work", "personal", "unclassified"):
        (tmp_path / sub).mkdir()
    return tmp_path


@pytest.fixture
def config(tmp_output: Path) -> PipelineConfig:
    """PipelineConfig pointing at the temporary output directory."""
    return PipelineConfig(output_directory=str(tmp_output))


@pytest.fixture
def registry() -> NoteRegistry:
    return NoteRegistry()


@pytest.fixture
def svg_store(config: PipelineConfig) -> SvgStore:
    return SvgStore(config.output_directory)


@pytest.fixture
def json_store(config: PipelineConfig) -> JsonStore:
    return JsonStore(config.output_directory)


@pytest.fixture
def markdown_store(config: PipelineConfig) -> MarkdownStore:
    return MarkdownStore(config.output_directory)


@pytest.fixture
def collision_resolver(config: PipelineConfig) -> CollisionResolver:
    return CollisionResolver(config.output_directory)


@pytest.fixture
def pipeline(
    config: PipelineConfig,
    registry: NoteRegistry,
    svg_store: SvgStore,
    json_store: JsonStore,
    markdown_store: MarkdownStore,
    collision_resolver: CollisionResolver,
) -> SyncPipeline:
    return SyncPipeline(
        config=config,
        registry=registry,
        svg_store=svg_store,
        json_store=json_store,
        markdown_store=markdown_store,
        collision_resolver=collision_resolver,
    )


@pytest.fixture
def mock_device() -> X10Device:
    device = X10Device(address="AA:BB:CC:DD:EE:FF")
    device.stored_pages = [
        Page(page_id="page-001"),
        Page(page_id="page-002"),
    ]
    device.page_count = 2
    return device


@pytest.fixture
def mock_page() -> Page:
    return Page(page_id="page-test-001")


@pytest.fixture
def mock_user() -> MagicMock:
    return MagicMock(name="User")
