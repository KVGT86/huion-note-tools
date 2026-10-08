from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timezone

import pytest
import yaml
from PIL import Image

from huion_note_pipeline import application
from huion_note_pipeline.application import HuionApplication
from huion_note_pipeline.models import Note


def configured_service(pipeline, tmp_output, monkeypatch):
    vault = tmp_output / "Caleb Vault"
    (vault / ".obsidian").mkdir(parents=True)
    config_file = tmp_output / "config.json"
    config = {"obsidian_vault": str(vault)}
    monkeypatch.setattr(application, "load_config", lambda: config.copy())
    monkeypatch.setattr(
        application, "save_config",
        lambda value: (config.clear(), config.update(value), config_file.write_text("{}")))
    monkeypatch.setattr("huion.ble.CONFIG_PATH", str(config_file))
    return HuionApplication(pipeline, MagicMock()), vault


def frontmatter(markdown: str) -> dict:
    return yaml.safe_load(markdown.split("---", 2)[1])


def test_obsidian_publish_is_mobile_friendly_and_updates_by_stable_id(pipeline, tmp_output, monkeypatch):
    service, vault = configured_service(pipeline, tmp_output, monkeypatch)
    svg = Path(service.save_live_page([[(1000, 1000, 3000), (8000, 9000, 5000)]]))
    note = next(note for note in service.load_notes() if note.svg_path == str(svg))
    transcript = svg.with_suffix(".md")
    transcript.write_text("---\nlegacy: true\n---\n# Old title\n\nReviewed transcript…\n", encoding="utf-8")
    note.markdown_path = str(transcript)
    service.update_note_metadata(note, title="Meeting notes", tags=["client", "follow-up"],
                                 collection="Rewa", favourite=True, reviewed=True)

    published = service.publish_to_obsidian([note])
    stable_id = service.huion_id(note)
    markdown_path = vault / "00 Inbox" / "Huion" / f"{note.synced_at:%Y-%m-%d}-meeting-notes.md"
    image_path = vault / "00 Inbox" / "Huion Attachments" / f"{stable_id}.png"
    assert published == [str(markdown_path), str(image_path)]
    markdown = markdown_path.read_text(encoding="utf-8")
    properties = frontmatter(markdown)
    assert properties == {
        "title": "Meeting notes", "date": note.synced_at.date(), "source": "huion",
        "huion_id": stable_id, "status": "inbox", "tags": ["client", "follow-up"],
        "collection": "Rewa", "favourite": True, "reviewed": True,
    }
    assert "# Meeting notes\n\nReviewed transcript…" in markdown
    assert f"![[{stable_id}.png]]" in markdown
    assert not list(vault.rglob("*.svg")) and not list(vault.rglob("*.json"))
    with Image.open(image_path) as image:
        assert image.size == (1410, 1870) and image.format == "PNG"

    transcript.write_text("# Meeting notes\n\nUpdated transcript.\n", encoding="utf-8")
    service.update_note_metadata(note, title="Renamed meeting", tags=[], collection="",
                                 favourite=False, reviewed=False)
    assert service.publish_to_obsidian([note]) == [str(markdown_path), str(image_path)]
    assert "Updated transcript." in markdown_path.read_text(encoding="utf-8")
    assert len(list((vault / "00 Inbox" / "Huion").glob("*.md"))) == 1
    assert len(list((vault / "00 Inbox" / "Huion Attachments").glob("*.png"))) == 1


def test_obsidian_publish_refuses_unrelated_filename_collision(pipeline, tmp_output, monkeypatch):
    service, vault = configured_service(pipeline, tmp_output, monkeypatch)
    svg = Path(service.save_live_page([[(1000, 1000, 3000)]]))
    note = next(note for note in service.load_notes() if note.svg_path == str(svg))
    service.update_note_metadata(note, title="Collision", tags=[], collection="", favourite=False)
    target = vault / "00 Inbox" / "Huion" / f"{note.synced_at:%Y-%m-%d}-collision.md"
    target.parent.mkdir(parents=True)
    target.write_text("---\nhuion_id: someone-else\n---\n")
    with pytest.raises(FileExistsError, match="different Huion ID"):
        service.publish_to_obsidian([note])
    assert target.read_text() == "---\nhuion_id: someone-else\n---\n"
    assert not list((vault / "00 Inbox" / "Huion Attachments").glob("*.png"))


def test_obsidian_requires_a_real_vault(pipeline, monkeypatch):
    monkeypatch.setattr(application, "load_config", lambda: {})
    service = HuionApplication(pipeline, MagicMock())
    with pytest.raises(ValueError, match="Choose your Obsidian vault"):
        service.publish_to_obsidian([MagicMock()])


def test_offline_page_id_survives_library_moves(tmp_path):
    first = tmp_path / "first" / "page.json"
    second = tmp_path / "moved" / "renamed.json"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text('{"strokes":[{"points":[1,2,3]}]}')
    second.write_bytes(first.read_bytes())
    svg = tmp_path / "page.svg"
    svg.write_text("<svg/>")
    now = datetime.now(timezone.utc)
    one = Note(str(svg), str(first), now)
    two = Note(str(svg), str(second), now)
    assert HuionApplication.huion_id(one) == HuionApplication.huion_id(two)
