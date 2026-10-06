import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from huion_note_pipeline.config import PipelineConfig
from huion_note_pipeline.gui.qt_app import HuionNoteWindow
from huion_note_pipeline.pipeline import NoteRegistry, SyncPipeline
from huion_note_pipeline.store import CollisionResolver, JsonStore, MarkdownStore, SvgStore


class FakeBridge:
    _stream_thread = None
    _is_connected = False
    _last_battery = None

    def on_pen_point(self, callback):
        self.pen_callback = callback

    def on_hardware_button(self, callback):
        self.button_callback = callback

    def stop_pen_input(self):
        pass

    def stream_pen_input(self, mac, mode="tablet"):
        self.started = (mac, mode)


def test_qt_shell_builds_and_routes(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    config = PipelineConfig(str(tmp_path))
    pipeline = SyncPipeline(
        config,
        NoteRegistry(),
        SvgStore(str(tmp_path)),
        JsonStore(str(tmp_path)),
        MarkdownStore(str(tmp_path)),
        CollisionResolver(str(tmp_path)),
    )
    window = HuionNoteWindow(pipeline, FakeBridge())
    assert app.style().objectName() == "fusion"
    assert window.no_selection.isHidden() is False
    assert window.filter.accessibleName() == "Filter pages by transcript status"
    window.filter.showPopup()
    app.processEvents()
    assert window.filter.view().sizeHintForRow(0) >= 32
    window.filter.hidePopup()
    from PySide6.QtGui import QPalette
    assert window.search.palette().color(QPalette.ColorRole.PlaceholderText).name() == "#625f59"

    assert window.pages.count() == 2
    assert window.pages.currentIndex() == 0
    assert window.page_title.text() == "Notes"
    window._show_page(1)
    assert window.page_title.text() == "Live notebook"
    assert window.statusbar.isAncestorOf(window.live_view_controls)
    assert window.statusbar.isAncestorOf(window.device_label)
    assert window.live_hint.text() == "Blank page"
    assert not window.previous_page_button.isEnabled()
    assert not window.next_page_button.isEnabled()
    from PySide6.QtWidgets import QToolButton
    zoom_in = next(b for b in window.live_view_controls.findChildren(QToolButton)
                   if b.accessibleName() == "Zoom in")
    assert not zoom_in.icon().isNull()
    zoom_in.click()
    assert window.canvas.zoom == 1.2
    from types import SimpleNamespace
    window.canvas.add_point(SimpleNamespace(x=4000, y=5000, pressure=1000, touch=True))
    window.canvas.add_point(SimpleNamespace(x=5000, y=6000, pressure=6000, touch=True))
    window.canvas.add_point(SimpleNamespace(x=5000, y=6000, pressure=0, touch=False))
    first = window.canvas.samples()
    assert window.live_hint.text() == "Unsaved changes"
    def fail_draft(strokes):
        raise OSError("Notes folder is unavailable")
    with monkeypatch.context() as patch:
        patch.setattr(window.service, "save_live_draft", fail_draft)
        assert not window.save_draft()
        assert window.live_hint.text() == "Draft not saved"
    assert window.save_draft()
    assert window.live_hint.text() == "Draft saved"
    window.new_page()
    assert window.canvas.samples() == []
    assert window.previous_page_button.isEnabled()
    assert window.live_hint.text() == "Blank page"
    window.canvas.add_point(SimpleNamespace(x=10000, y=5000, pressure=2000, touch=True))
    current = window.canvas.samples()
    window.browse_live(-1)
    assert window.canvas.samples() == first
    assert window.next_page_button.isEnabled()
    assert window.live_hint.text() == "Saved page"
    window.save_live()
    window.browse_live(1)
    assert window.canvas.samples() == current
    window.resize(860, 580)
    window.show()
    app.processEvents()
    assert window.live_toolbar.width() >= window.live_toolbar.minimumSizeHint().width()
    assert window.live_view_controls.geometry().right() < window.statusbar.width()
    window.toggle_presentation()
    assert window._presentation and not window.sidebar.isVisible()
    assert window.statusbar.isHidden()
    window.leave_presentation()
    assert not window._presentation
    assert not window.statusbar.isHidden()
    from PySide6.QtCore import Qt
    window.resize(860, 580)
    window._show_page(0)
    window.note_list.setCurrentRow(0)
    assert window.no_selection.isHidden()
    window.detail_tabs.setCurrentIndex(2)
    window.show()
    app.processEvents()
    window.adapt_review()
    assert window.review_splitter.orientation() == Qt.Orientation.Vertical
    window.filter.setCurrentIndex(2)
    assert window.note_list.count() == 0
    assert window.no_selection.isHidden() is False
    assert not window.save_transcript_button.isEnabled()
    window.filter.setCurrentIndex(0)
    window.note_list.setCurrentRow(0)
    window.editor.setPlainText("Reviewed transcript")
    assert window.save_transcript_button.isEnabled()
    assert window.save_transcript()
    assert not window.save_transcript_button.isEnabled()
    window.close()
    app.processEvents()
    import json
    assert json.loads((tmp_path / ".live-draft.json").read_text())["strokes"] == [[list(p) for p in s] for s in current]
