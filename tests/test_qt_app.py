import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from huion_note_pipeline.config import PipelineConfig
from huion_note_pipeline.gui.qt_app import HuionNoteWindow, ICON_NAMES, ICONS, ui_icon
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


def test_delete_confirmation_and_history_keep_live_ink(pipeline, monkeypatch):
    from pathlib import Path
    from PySide6.QtCore import QTimer
    from huion_note_pipeline.application import HuionApplication, DeviceSnapshot
    app = QApplication.instance() or QApplication([])
    service = HuionApplication(pipeline, FakeBridge())
    strokes = [[(1000, 1000, 2000), (2000, 2000, 4000)]]
    path = service.save_live_page(strokes)
    service.registry.load_from_disk(service.output_directory)
    monkeypatch.setattr(service, "load_notes", service.registry.all)
    window = HuionNoteWindow(service=service)
    window.note_list.setCurrentRow(0)
    jobs = []
    monkeypatch.setattr(window, "run_job", lambda name, work: jobs.append((name, work)))
    QTimer.singleShot(0, lambda: app.activeModalWidget().defaultButton().click())
    window.delete_selected()
    assert not jobs and Path(path).exists()
    def accept():
        modal = app.activeModalWidget()
        next(b for b in modal.buttons() if b.text() == "Move to Trash").click()
    QTimer.singleShot(0, accept)
    window.delete_selected()
    assert jobs[0][0] == "Delete" and Path(path).exists()  # Worker not run in this UI check.
    window.canvas.set_samples(strokes)
    window._live_history = [strokes]
    window._live_paths = [str(Path(service.output_directory) / "missing.svg")]
    window._history_index = 1
    window.refresh_live_history()
    assert window.canvas.samples() == strokes and not window._live_history
    for count, text in ((12, "~38/50 free"), (60, "~0/50 free")):
        monkeypatch.setattr(service, "device_snapshot", lambda count=count: DeviceSnapshot(False, None, count, "test sync"))
        window.refresh_connection()
        assert text in window.storage_label.text()
        assert "last complete sync" in window.storage_label.toolTip()
    window._busy = True
    window.selection_changed()
    assert not window.delete_button.isEnabled()
    window._busy = False
    window.close()


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
    from PySide6.QtSvg import QSvgRenderer
    for name, filename in ICON_NAMES.items():
        assert QSvgRenderer(str(ICONS / f"{filename}.svg")).isValid()
        assert not ui_icon(name).pixmap(18, 18).isNull()
    assert (ICONS / "LICENSE").exists()
    assert (ICONS / "check.svg").read_text() == (ICONS / "check-white.svg").read_text().replace("#FFFFFF", "currentColor")
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
    assert not window.delete_button.isEnabled()
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
    assert window.statusbar.height() >= 56
    from PySide6.QtCore import QPoint
    controls_top = window.live_view_controls.mapTo(window.statusbar, QPoint(0, 0)).y()
    assert controls_top >= 8
    assert controls_top + window.live_view_controls.height() <= window.statusbar.height() - 8
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
    assert window.delete_button.isEnabled()
    from PySide6.QtCore import QPoint
    action_bottom = window.export_button.mapTo(window, QPoint(0, window.export_button.height())).y()
    footer_top = window.statusbar.mapTo(window, QPoint(0, 0)).y()
    assert footer_top - action_bottom >= 16
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
