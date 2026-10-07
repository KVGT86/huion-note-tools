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

    def __init__(self):
        self.modes = []

    def on_pen_point(self, callback):
        self.pen_callback = callback

    def on_hardware_button(self, callback):
        self.button_callback = callback

    def stop_pen_input(self):
        pass

    def stream_pen_input(self, mac, mode="tablet"):
        self.started = (mac, mode)
        self.modes.append(mode)

    def retry_connection(self, mac, mode="tablet"):
        self.modes.append(mode)


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
    assert window.service.bridge.modes == ["notes"]
    from huion_note_pipeline.application import DeviceSnapshot
    monkeypatch.setattr(window.service, "device_snapshot", lambda: DeviceSnapshot(True, 80))
    window.refresh_connection()
    assert window.device_label.text() == "X10 paired · 80%"
    from PySide6.QtWidgets import QAbstractItemView
    assert window.note_list.selectionMode() == QAbstractItemView.SelectionMode.MultiSelection
    assert not window.delete_button.isEnabled()
    window._show_page(1)
    assert window.page_title.text() == "Live notebook"
    assert window.service.bridge.modes[-1] == "tablet"
    window.refresh_connection()
    assert window.device_label.text() == "X10 live · 80%"
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
    def fail_draft(*args):
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
    window.change_ink("#2457A7")
    assert window.ink_button.text() == "Blue"
    window.browse_live(-1)
    assert window.canvas.samples() == first
    assert window.next_page_button.isEnabled()
    assert window.live_hint.text() == "Saved page"
    window.save_live()
    window.browse_live(1)
    assert window.canvas.samples() == current
    from PySide6.QtGui import QColor
    monkeypatch.setattr("huion_note_pipeline.gui.qt_app.QColorDialog.getColor", lambda *a: QColor())
    window.choose_ink()
    assert window.canvas.ink_color == "#2457A7"
    monkeypatch.setattr("huion_note_pipeline.gui.qt_app.QColorDialog.getColor", lambda *a: QColor("#765432"))
    window.choose_ink()
    assert window.ink_button.text() == "#765432"
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
    assert window.service.bridge.modes[-1] == "notes"
    window.note_list.setCurrentRow(0)
    assert window.delete_button.isEnabled()
    window.select_all_button.click()
    assert not window.note_list.selectedItems()
    assert window.select_all_button.text() == "Select all"
    window.select_all_button.click()
    assert len(window.note_list.selectedItems()) == window.note_list.count()
    assert window.select_all_button.text() == "Clear selection"
    window.note_list.setCurrentRow(0)
    from PySide6.QtCore import QPoint
    action_bottom = window.export_button.mapTo(window, QPoint(0, window.export_button.height())).y()
    footer_top = window.statusbar.mapTo(window, QPoint(0, 0)).y()
    assert footer_top - action_bottom >= 16
    card = window.note_list.visualItemRect(window.note_list.item(0))
    image = window.note_list.viewport().grab().toImage()
    center_y = min(image.height() - 1, card.center().y())
    assert image.pixelColor(1, center_y).name() == "#ffffff"
    assert image.pixelColor(image.width() - 2, center_y).name() == "#ffffff"
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


def test_live_overlap_is_solid_for_active_and_completed_strokes():
    import math
    from types import SimpleNamespace
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from huion_note_pipeline.gui.qt_app import LiveCanvas
    app = QApplication.instance() or QApplication([])
    canvas = LiveCanvas()
    twice = [(14000 + 4000 * math.cos(i * math.tau / 160),
              14000 + 4000 * math.sin(i * math.tau / 160), 8192) for i in range(321)]
    def pixel():
        image = QImage(2820, 3740, QImage.Format.Format_RGB32)
        image.fill("white")
        painter = QPainter(image)
        canvas.paint_ink(painter, QRectF(0, 0, 2820, 3740))
        painter.end()
        return image.pixelColor(1400, 1800).name()
    canvas.set_samples([twice])
    assert pixel() == "#25231f"  # Odd-even fill left this retraced area white.
    canvas.clear_page()
    canvas.set_ink_color("#2457A7")
    for x, y, pressure in twice:
        canvas.add_point(SimpleNamespace(x=x, y=y, pressure=pressure, touch=True))
    canvas.set_ink_color("#912D47")  # Never recolour a stroke already in progress.
    assert pixel() == "#2457a7" and canvas.colors() == ["#2457A7"]
    canvas.add_point(SimpleNamespace(pressure=0, touch=False))
    assert pixel() == "#2457a7"
    canvas.add_point(SimpleNamespace(x=14000, y=18000, pressure=8192, touch=True))
    assert pixel() == "#912d47"  # New ink covers existing ink rather than cutting a hole.
    canvas.add_point(SimpleNamespace(pressure=0, touch=False))
    assert canvas.colors() == ["#2457A7", "#912D47"]
    assert 'fill="#2457A7"' in canvas.to_svg() and 'fill="#912D47"' in canvas.to_svg()
    canvas.close()
