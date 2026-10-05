import tempfile
from pathlib import Path
from huion_note_pipeline import htr
from huion_note_pipeline.models import Note
from huion_note_pipeline.enums import NoteStatus
from huion_note_pipeline.editor import NoteEditorPage
from datetime import datetime, timezone
import tkinter as tk

MINIMAL_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1190">
  <path d="M 100,100 L 200,200 L 300,200" stroke="#111" stroke-width="2" fill="none"/>
</svg>"""

def test_to_markdown():
    raw = "MEETING NOTES\n- Discuss architecture\n- Review budget\n1. First item\nAction items\nDo the thing."
    md = htr.to_markdown(raw, title="Sprint Review")
    assert "# Sprint Review" in md
    assert "## Meeting Notes" in md
    assert "- Discuss architecture" in md
    assert "1. First item" in md

def test_rasterise_svg():
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
        f.write(MINIMAL_SVG.encode("utf-8"))
        tmp_svg = f.name

    try:
        png_bytes = htr.rasterise_svg(tmp_svg)
        assert len(png_bytes) > 0
        assert png_bytes.startswith(b"\x89PNG")
    finally:
        Path(tmp_svg).unlink(missing_ok=True)

def test_editor_load_and_save():
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
        f.write(MINIMAL_SVG.encode("utf-8"))
        tmp_svg = f.name

    root = tk.Tk()
    root.withdraw()
    try:
        note = Note(
            svg_path=tmp_svg,
            json_path=tmp_svg,
            synced_at=datetime.now(timezone.utc),
            status=NoteStatus.SYNCED
        )
        saved = []
        def on_save(n):
            saved.append(n)
        def on_back():
            pass

        editor = NoteEditorPage(root, note=note, on_save=on_save, on_back=on_back)
        assert len(editor._svg_strokes) >= 1

        # Simulate adding an annotation stroke
        editor._annotation_strokes.append([(150.0, 150.0), (250.0, 250.0)])
        editor._save()
        assert len(saved) == 1

        # Check saved content
        content = Path(tmp_svg).read_text()
        assert 'stroke="#1C1C1C"' in content
    finally:
        root.destroy()
        Path(tmp_svg).unlink(missing_ok=True)
        Path(tmp_svg).with_suffix(".bak.svg").unlink(missing_ok=True)
