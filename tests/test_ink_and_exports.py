import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from huion.ink import outline, svg_document
from huion.models import Stroke, PenPoint
from huion.renderer import MultiFormatRenderer
from huion_note_pipeline.application import HuionApplication


def test_ink_keeps_dots_and_local_pressure():
    dot = outline([(1000, 1000, 4096)])
    assert len(dot) == 16
    points = [(1000, 1000, 1), (2000, 1000, 8192), (3000, 1000, 1)]
    shape = outline(points)
    assert max(y for x, y in shape if 1800 < x < 2200) - 1000 > 30
    assert max(y for x, y in shape if x < 1100) - 1000 < 16
    assert points == [(1000, 1000, 1), (2000, 1000, 8192), (3000, 1000, 1)]
    assert outline([(float("nan"), 1, 1)]) == []
    assert 'fill="#25231F"' in svg_document([[(1000, 1000, 4096)]])


def test_renderer_png_and_json_preserve_ink(tmp_path):
    from PIL import Image
    renderer = MultiFormatRenderer()
    strokes = [Stroke([PenPoint(1000, 1000, 4000)])]
    renderer.export_all(strokes, str(tmp_path), "dot")
    assert json.loads((tmp_path / "dot.json").read_text())["strokes"][0]["points"][0]["pressure"] == 4000
    image = Image.open(tmp_path / "dot.png")
    assert image.size == (2820, 3740)
    assert image.getpixel((100, 100))[0] < 100
    assert (tmp_path / "dot.svg").read_text() == renderer.svg(strokes)


def test_live_recovery_and_collision_safe_exports(pipeline, tmp_output):
    service = HuionApplication(pipeline, MagicMock())
    strokes = [[(1000, 1000, 3000), (2000, 2500, 5000)]]
    path = Path(service.save_live_page(strokes))
    recovered = HuionApplication(pipeline, MagicMock())
    assert recovered.live_draft() == [[list(p) for p in s] for s in strokes]
    assert recovered.save_live_page(strokes) == str(path)
    note = next(n for n in service.load_notes() if n.svg_path == str(path))
    exported = service.export_notes([note], str(tmp_output / "exports"), ["svg", "json", "pdf", "png"])
    assert len(exported) == 4
    assert Path(exported[2]).read_bytes().startswith(b"%PDF")
    again = service.export_notes([note], str(tmp_output / "exports"), ["svg"])
    assert exported[0] != again[0]
    assert Path(exported[0]).read_text() == Path(again[0]).read_text()
    service.new_live_page()
    assert service.live_draft() == []
    assert path.exists()


def test_existing_transcript_loads_on_restart(pipeline, tmp_output):
    svg = tmp_output / "existing.svg"
    svg.write_text(svg_document([[(1000, 1000, 4000)]]))
    svg.with_suffix(".md").write_text("# Existing transcript")
    note = next(n for n in pipeline.registry.load_from_disk(str(tmp_output)) if n.svg_path == str(svg))
    assert note.markdown_path == str(svg.with_suffix(".md"))


def test_repeated_sync_names_do_not_replace_or_hide_pages(pipeline, tmp_output):
    from huion.sync_engine import next_sync_folder
    first = Path(next_sync_folder(str(tmp_output), "2026-10-06")) / "page.svg"
    first.write_text(svg_document([[(1000, 1000, 1000)]]))
    second = Path(next_sync_folder(str(tmp_output), "2026-10-06")) / "page.svg"
    second.write_text(svg_document([[(2000, 2000, 2000)]]))
    notes = pipeline.registry.load_from_disk(str(tmp_output))
    assert first != second and len(notes) == 2
    assert first.read_text() != second.read_text()


def test_markdown_export_bundle_preserves_sketches(pipeline, tmp_output):
    service = HuionApplication(pipeline, MagicMock())
    path = Path(service.save_live_page([[(1000, 1000, 4000)]]))
    note = next(n for n in service.load_notes() if n.svg_path == str(path))
    service.save_markdown(note, f"# Page\n\n![Sketch]({path.name})")
    files = service.export_notes([note], str(tmp_output / "export"), ["md"])
    assert (Path(files[0]).parent / path.name).exists()
    second = service.export_notes([note], str(tmp_output / "export"), ["md"])
    assert Path(files[0]).parent != Path(second[0]).parent


def test_invalid_live_draft_is_preserved(pipeline, tmp_output):
    service = HuionApplication(pipeline, MagicMock())
    (tmp_output / ".live-draft.json").write_text("broken original draft")
    with pytest.raises(ValueError):
        service.live_draft()
    service.save_live_draft([])
    assert next(tmp_output.glob(".live-draft-recovery-*.json")).read_text() == "broken original draft"


def test_cloud_transcription_handles_empty_and_failed_responses(monkeypatch):
    from huion_note_pipeline import htr
    monkeypatch.setattr(htr, "rasterise_svg", lambda _: b"image")
    response = MagicMock(ok=True)
    response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "Thinking", "thought": True}, {"text": "Notebook text"}]}}]}
    post = MagicMock(return_value=response)
    monkeypatch.setattr("requests.post", post)
    assert htr.run_ocr_gemini("fake.svg", api_key="test-only") == "Notebook text"
    assert post.call_args.kwargs["headers"]["x-goog-api-key"] == "test-only"
    response.json.return_value = {"candidates": []}
    with pytest.raises(RuntimeError, match="did not return"):
        htr.run_ocr_gemini("fake.svg", api_key="test-only")
    response.ok = False
    response.status_code = 429
    with pytest.raises(RuntimeError, match="quota"):
        htr.run_ocr_gemini("fake.svg", api_key="test-only")


def test_sync_timeout_cancels_the_pending_transfer(monkeypatch):
    from huion_note_pipeline.ble_bridge import DeviceBridge
    bridge = DeviceBridge()
    bridge._current_loop = MagicMock()
    bridge._current_conn = MagicMock()
    bridge._is_connected = True
    bridge._async_sync_active_conn = lambda *args: object()
    future = MagicMock()
    future.result.side_effect = TimeoutError()
    monkeypatch.setattr("asyncio.run_coroutine_threadsafe", lambda *args: future)
    with pytest.raises(TimeoutError, match="Already saved pages"):
        bridge.sync_offline_pages("not-used")
    future.cancel.assert_called_once()


def test_launchers_share_saved_folder_and_environment_override(monkeypatch, tmp_path):
    from huion_note_pipeline import application
    config_file = tmp_path / "config.json"
    config_file.write_text("{}")
    monkeypatch.setattr("huion.ble.CONFIG_PATH", str(config_file))
    monkeypatch.setattr(application, "load_config", lambda: {"output_dir": str(tmp_path / "saved")})
    monkeypatch.delenv("HUION_NOTES_DIR", raising=False)
    assert application.create_application().output_directory == str(tmp_path / "saved")
    monkeypatch.setenv("HUION_NOTES_DIR", str(tmp_path / "override"))
    assert application.create_application().output_directory == str(tmp_path / "override")
