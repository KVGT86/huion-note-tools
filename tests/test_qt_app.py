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


def test_qt_shell_builds_and_routes(tmp_path):
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

    assert window.pages.count() == 2
    window._show_page(1)
    assert window.page_title.text() == "Document library"
    window.close()
    app.processEvents()
