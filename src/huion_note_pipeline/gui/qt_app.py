"""PySide6 desktop shell for HuionNote.

The GUI renders state and forwards user intent. Bluetooth, sync, storage, and
conversion remain in the existing ``huion`` and pipeline packages.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

# Qt 6.11 currently crashes rendering this window through Zorin's Wayland
# compositor. XWayland is stable and still preserves native desktop behavior.
if sys.platform.startswith("linux"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import PipelineConfig
from ..application import HuionApplication
from ..enums import NoteStatus
from ..models import Note
from ..pipeline import NoteRegistry, SyncPipeline


INK = "#25231F"
MUTED = "#625F59"
FAINT = "#706D67"
PAPER = "#FFFFFF"
WARM = "#F7F6F3"
HOVER = "#EEEDE8"
LINE = "#E3E1DC"
GREEN = "#23683A"
AMBER = "#7D480C"
RED = "#B43D35"


STYLE = f"""
* {{ font-size: 13px; color: {INK}; }}
QMainWindow, QWidget#content {{ background: {PAPER}; }}
QWidget#sidebar, QWidget#page {{ background: {WARM}; }}
QFrame#topbar {{ background: {PAPER}; border-bottom: 1px solid {LINE}; }}
QLabel#brand {{ font-size: 16px; font-weight: 600; }}
QLabel#subtle, QLabel#meta {{ color: {MUTED}; }}
QLabel#section {{ color: {FAINT}; font-size: 10px; font-weight: 600; }}
QLabel#title {{ font-size: 20px; font-weight: 600; }}
QLabel#emptyTitle {{ font-size: 17px; font-weight: 600; }}
QPushButton {{
    background: transparent; border: 0; border-radius: 7px; padding: 8px 10px;
    text-align: left;
}}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:focus {{ border: 1px solid #9C9A94; }}
QPushButton:checked {{ background: #E8E6E1; font-weight: 600; }}
QPushButton#primary {{ background: {INK}; color: white; padding: 8px 14px; text-align: center; }}
QPushButton#primary:hover {{ background: #11100E; }}
QPushButton#quiet {{ color: {MUTED}; }}
QPushButton#danger {{ color: {RED}; }}
QLabel#status {{ border-radius: 10px; padding: 4px 9px; font-size: 11px; font-weight: 600; }}
QFrame#noteRow {{ background: {PAPER}; border-bottom: 1px solid {LINE}; }}
QFrame#noteRow:hover {{ background: #FBFAF8; }}
QListWidget {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 10px; padding: 4px; }}
QListWidget::item {{ padding: 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: #E8E6E1; color: {INK}; }}
QLineEdit, QTextEdit {{ background: {PAPER}; border: 1px solid #D3D1CB; border-radius: 7px; padding: 8px; }}
QScrollArea {{ border: 0; background: {WARM}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px; }}
QScrollBar::handle:vertical {{ background: #C9C7C1; border-radius: 4px; min-height: 34px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


def _label(text: str, role: str = "") -> QLabel:
    label = QLabel(text)
    if role:
        label.setObjectName(role)
    return label


class LiveCanvas(QWidget):
    """A5 paper canvas; accepts device-space pen points and owns no BLE logic."""

    PAGE_W = 28200
    PAGE_H = 37400

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(420, 520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._strokes: list[list[tuple[float, float, int]]] = []
        self._active: list[tuple[float, float, int]] = []

    def add_point(self, point: Any) -> None:
        if bool(getattr(point, "touch", False)) or getattr(point, "pressure", 0) > 0:
            self._active.append((float(point.x), float(point.y), int(point.pressure)))
        elif self._active:
            self._strokes.append(self._active)
            self._active = []
        self.update()

    def clear_page(self) -> None:
        self._strokes.clear()
        self._active.clear()
        self.update()

    def _paper(self) -> QRectF:
        margin = 28.0
        available = self.rect().adjusted(int(margin), int(margin), -int(margin), -int(margin))
        ratio = 148 / 210
        height = min(available.height(), available.width() / ratio)
        width = height * ratio
        x = (self.width() - width) / 2
        y = (self.height() - height) / 2
        return QRectF(x, y, width, height)

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(WARM))
        page = self._paper()
        painter.fillRect(page, QColor(PAPER))
        painter.setPen(QPen(QColor("#D3D1CB"), 1))
        painter.drawRect(page)
        painter.setPen(QPen(QColor("#D4D1CA"), 1))
        step = 24
        x = page.left() + step
        while x < page.right():
            y = page.top() + step
            while y < page.bottom():
                painter.drawPoint(QPointF(x, y))
                y += step
            x += step
        for stroke in [*self._strokes, self._active]:
            if len(stroke) < 2:
                continue
            path = QPainterPath(self._map(stroke[0], page))
            for point in stroke[1:]:
                path.lineTo(self._map(point, page))
            pressure = sum(p[2] for p in stroke) / len(stroke)
            pen = QPen(QColor(INK), 0.8 + min(1.0, pressure / 8192) * 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)

    def _map(self, point: tuple[float, float, int], page: QRectF) -> QPointF:
        return QPointF(
            page.left() + point[0] / self.PAGE_W * page.width(),
            page.top() + point[1] / self.PAGE_H * page.height(),
        )

    def to_svg(self) -> str:
        lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.PAGE_W} {self.PAGE_H}">']
        for stroke in [*self._strokes, self._active]:
            if len(stroke) > 1:
                points = " ".join(f"{x:g},{y:g}" for x, y, _pressure in stroke)
                lines.append(f'  <polyline points="{points}" fill="none" stroke="#25231F" stroke-width="42" stroke-linecap="round" stroke-linejoin="round"/>')
        lines.append("</svg>")
        return "\n".join(lines)


class NoteRow(QFrame):
    action_requested = Signal(str, object)

    def __init__(self, note: Note) -> None:
        super().__init__()
        self.note = note
        self.setObjectName("noteRow")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 16, 12)
        copy = QVBoxLayout()
        title = Path(note.svg_path).stem.replace("_", " ").title()
        copy.addWidget(_label(title))
        date = note.synced_at.strftime("%d %b %Y · %H:%M") if note.synced_at else "Date unavailable"
        copy.addWidget(_label(date, "meta"))
        row.addLayout(copy, 1)
        status = _label(note.status.value.title(), "status")
        colors = {
            NoteStatus.CONVERTED: ("#E8F3EB", GREEN),
            NoteStatus.CONVERTING: ("#FFF3DF", AMBER),
            NoteStatus.FAILED: ("#FBE9E7", RED),
            NoteStatus.SYNCED: ("#EFEEEA", MUTED),
        }[note.status]
        status.setStyleSheet(f"background:{colors[0]}; color:{colors[1]};")
        row.addWidget(status)
        if note.status == NoteStatus.FAILED:
            actions = [("View", "view"), ("Edit", "edit"), ("Retry", "retry")]
        elif note.status in (NoteStatus.CONVERTING, NoteStatus.CONVERTED):
            actions = [("View", "view"), ("Edit", "edit")]
        else:
            actions = [("View", "view"), ("Edit", "edit"), ("OCR", "ocr"), ("AI", "ai")]
        for label, action in actions:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, a=action: self.action_requested.emit(a, self.note))
            row.addWidget(button)


class SettingsDialog(QDialog):
    def __init__(self, output_dir: str, gemini_key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        form.setContentsMargins(24, 24, 24, 24)
        self.output = QLineEdit(output_dir)
        self.gemini = QLineEdit(gemini_key)
        self.gemini.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Notes folder", self.output)
        form.addRow("Gemini API key", self.gemini)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class HuionNoteWindow(QMainWindow):
    pen_received = Signal(object)
    hardware_button_received = Signal()
    sync_finished = Signal(object)
    sync_failed = Signal(str)
    conversion_finished = Signal(object)
    conversion_started = Signal(object)
    conversion_failed = Signal(object, str)
    clear_finished = Signal()
    clear_failed = Signal(str)

    def __init__(
        self,
        pipeline: Optional[SyncPipeline] = None,
        bridge: Any = None,
        service: Optional[HuionApplication] = None,
        registry: Optional[NoteRegistry] = None,
        config: Optional[PipelineConfig] = None,
    ) -> None:
        super().__init__()
        if service is None:
            if pipeline is None or bridge is None:
                raise ValueError("pipeline and bridge are required when service is not supplied")
            service = HuionApplication(pipeline, bridge)
        self.service = service
        self.pipeline = service.pipeline
        self.registry = registry or service.registry
        self.config = config or service.config
        self._syncing = False
        self.setWindowTitle("HuionNote")
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(STYLE)
        icon = Path(__file__).resolve().parents[2] / "assets" / "huionnote.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self._build()
        self.pen_received.connect(self.canvas.add_point)
        self.hardware_button_received.connect(self._clear_canvas)
        self.sync_finished.connect(self._sync_complete)
        self.sync_failed.connect(self._sync_error)
        self.service.on_pen_point(self.pen_received.emit)
        self.service.on_hardware_button(self.hardware_button_received.emit)
        self.conversion_finished.connect(self._conversion_complete)
        self.conversion_started.connect(lambda _note: self.refresh_notes())
        self.conversion_failed.connect(self._conversion_error)
        self.clear_finished.connect(self._clear_complete)
        self.clear_failed.connect(self._clear_error)
        self._connection_timer = QTimer(self)
        self._connection_timer.timeout.connect(self._refresh_connection)
        self._connection_timer.start(1500)
        self.service.start_stream()
        self.load_library()

    def _build(self) -> None:
        shell = QWidget()
        shell.setObjectName("content")
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._sidebar())
        content = QWidget()
        content.setObjectName("content")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._topbar())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._live_page())
        self.pages.addWidget(self._library_page())
        column.addWidget(self.pages, 1)
        self.activity = QTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumHeight(120)
        self.activity.setPlaceholderText("Connection and sync activity will appear here.")
        self.activity.setVisible(False)
        column.addWidget(self.activity)
        root.addWidget(content, 1)
        self.setCentralWidget(shell)

    def _sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(224)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 18, 12, 14)
        layout.setSpacing(4)
        layout.addWidget(_label("HuionNote", "brand"))
        layout.addWidget(_label("Your notebook, in motion", "subtle"))
        layout.addSpacing(20)
        layout.addWidget(_label("WORKSPACE", "section"))
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        for index, text in enumerate(("Live canvas", "Document library")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, i=index: self._show_page(i))
            self.nav.addButton(button, index)
            layout.addWidget(button)
            if index == 0:
                button.setChecked(True)
        layout.addSpacing(18)
        layout.addWidget(_label("DEVICE", "section"))
        retry = QPushButton("Retry connection")
        retry.clicked.connect(self._retry_connection)
        layout.addWidget(retry)
        layout.addStretch(1)
        activity = QPushButton("Activity log")
        activity.clicked.connect(lambda: self.activity.setVisible(not self.activity.isVisible()))
        layout.addWidget(activity)
        settings = QPushButton("Settings")
        settings.clicked.connect(self.open_settings)
        layout.addWidget(settings)
        layout.addWidget(_label("v1.1 · Qt preview", "meta"))
        return sidebar

    def _topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 12, 20, 12)
        self.page_title = _label("Live canvas", "title")
        layout.addWidget(self.page_title)
        layout.addStretch(1)
        self.top_status = _label("●  Connecting", "status")
        self.top_status.setStyleSheet(f"background:#FFF3DF; color:{AMBER};")
        layout.addWidget(self.top_status)
        self.sync_button = QPushButton("Sync now")
        self.sync_button.setObjectName("primary")
        self.sync_button.clicked.connect(self.sync_now)
        layout.addWidget(self.sync_button)
        self.clear_device_button = QPushButton("Clear device")
        self.clear_device_button.setObjectName("danger")
        self.clear_device_button.clicked.connect(self.clear_device)
        self.clear_device_button.setVisible(False)
        layout.addWidget(self.clear_device_button)
        return bar

    def _live_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 16, 24, 24)
        header = QHBoxLayout()
        header.addWidget(_label("A5 · live ink", "meta"))
        header.addStretch(1)
        clear = QPushButton("Clear canvas")
        clear.clicked.connect(self._clear_canvas)
        header.addWidget(clear)
        export = QPushButton("Export SVG")
        export.clicked.connect(self.export_canvas)
        header.addWidget(export)
        layout.addLayout(header)
        self.canvas = LiveCanvas()
        layout.addWidget(self.canvas, 1)
        return page

    def _library_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 18, 24, 24)
        header = QHBoxLayout()
        self.library_count = _label("0 pages", "meta")
        header.addWidget(self.library_count)
        self.filters = QButtonGroup(self)
        self.filters.setExclusive(True)
        for label in ("All", "Queued", "Converted", "Failed"):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(self.refresh_notes)
            self.filters.addButton(button)
            header.addWidget(button)
            if label == "All":
                button.setChecked(True)
        header.addStretch(1)
        refresh = QPushButton("Rescan")
        refresh.clicked.connect(self.load_library)
        header.addWidget(refresh)
        layout.addLayout(header)
        self.notes_host = QWidget()
        self.notes_host.setObjectName("page")
        self.notes_layout = QVBoxLayout(self.notes_host)
        self.notes_layout.setContentsMargins(0, 0, 0, 0)
        self.notes_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.notes_host)
        layout.addWidget(scroll, 1)
        return page

    def _show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.page_title.setText("Live canvas" if index == 0 else "Document library")
        self.clear_device_button.setVisible(index == 1)

    def _refresh_connection(self) -> None:
        snapshot = self.service.device_snapshot()
        if snapshot.connected is True:
            battery = snapshot.battery
            text = f"●  Connected{f' · {battery}%' if battery is not None else ''}"
            style = f"background:#E8F3EB; color:{GREEN};"
        elif snapshot.connected is None:
            text, style = "●  Connecting", f"background:#FFF3DF; color:{AMBER};"
        else:
            text, style = "●  Disconnected", f"background:#EFEEEA; color:{MUTED};"
        self.top_status.setText(text)
        self.top_status.setStyleSheet(style)

    def _retry_connection(self) -> None:
        self.log("Retrying connection…")
        threading.Thread(target=self.service.retry_connection, daemon=True).start()

    def _clear_canvas(self) -> None:
        self.canvas.clear_page()
        self.log("Canvas cleared")

    def export_canvas(self) -> None:
        path, _selected = QFileDialog.getSaveFileName(self, "Export live canvas", "huion-note.svg", "SVG files (*.svg)")
        if path:
            Path(path).write_text(self.canvas.to_svg(), encoding="utf-8")
            self.log(f"Canvas exported · {path}")

    def load_library(self) -> None:
        self._all_notes = self.service.load_notes()
        self.refresh_notes()

    def refresh_notes(self) -> None:
        while self.notes_layout.count():
            item = self.notes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        selected = next((button.text() for button in self.filters.buttons() if button.isChecked()), "All")
        statuses = {"Queued": NoteStatus.SYNCED, "Converted": NoteStatus.CONVERTED, "Failed": NoteStatus.FAILED}
        notes = [note for note in self._all_notes if selected == "All" or note.status == statuses[selected]]
        converted = sum(note.status == NoteStatus.CONVERTED for note in self._all_notes)
        failed = sum(note.status == NoteStatus.FAILED for note in self._all_notes)
        self.library_count.setText(f"{len(notes)} shown · {converted} converted · {failed} need attention")
        if not notes:
            empty = QWidget()
            box = QVBoxLayout(empty)
            box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(_label("Your notebook is quiet", "emptyTitle"), alignment=Qt.AlignmentFlag.AlignCenter)
            box.addWidget(_label("Sync the X10 to bring handwritten pages into your library.", "subtle"), alignment=Qt.AlignmentFlag.AlignCenter)
            self.notes_layout.addWidget(empty, 1)
        else:
            for note in notes:
                row = NoteRow(note)
                row.action_requested.connect(self.note_action)
                self.notes_layout.addWidget(row)
            self.notes_layout.addStretch(1)
        self.log(f"Indexed {len(self._all_notes)} pages")

    def note_action(self, action: str, note: Note) -> None:
        if action == "view":
            self.open_note(note)
        elif action == "edit":
            self.edit_note(note)
        else:
            self.convert_note(note, cloud=action == "ai")

    def open_note(self, note: Note) -> None:
        path = note.markdown_path or note.svg_path
        if path:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def edit_note(self, note: Note) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit · {Path(note.svg_path).stem.replace('_', ' ').title()}")
        dialog.resize(720, 560)
        layout = QVBoxLayout(dialog)
        layout.addWidget(_label("Markdown companion", "title"))
        editor = QTextEdit()
        markdown = Path(note.markdown_path) if note.markdown_path else Path(note.svg_path).with_suffix(".md")
        if markdown.exists():
            editor.setPlainText(markdown.read_text(encoding="utf-8"))
        layout.addWidget(editor, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.service.save_markdown(note, editor.toPlainText())
                self.log(f"Saved · {markdown.name}")
                self.load_library()
            except Exception as exc:
                QMessageBox.warning(self, "Save failed", str(exc))

    def convert_note(self, note: Note, cloud: bool) -> None:
        if cloud and not self.service.gemini_key:
            QMessageBox.information(self, "Gemini key required", "Add your Gemini API key in Settings, then try again.")
            return
        self.log(f"{'AI' if cloud else 'OCR'} conversion started · {Path(note.svg_path).name}")
        def work() -> None:
            try:
                self.conversion_finished.emit(self.service.convert(
                    note,
                    cloud=cloud,
                    on_started=self.conversion_started.emit,
                ))
            except Exception as exc:
                self.conversion_failed.emit(note, str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _conversion_complete(self, note: Note) -> None:
        self.log(f"Conversion complete · {Path(note.svg_path).name}")
        self.load_library()

    def _conversion_error(self, note: Note, message: str) -> None:
        self.log(f"Conversion failed · {message}")
        self.refresh_notes()
        QMessageBox.warning(self, "Conversion failed", message)

    def sync_now(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        self.sync_button.setEnabled(False)
        self.sync_button.setText("Syncing…")
        self.log("Sync started")

        def work() -> None:
            try:
                pages = self.service.sync()
                self.sync_finished.emit(pages)
            except Exception as exc:
                self.sync_failed.emit(str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _sync_complete(self, pages: object) -> None:
        self._syncing = False
        self.sync_button.setEnabled(True)
        self.sync_button.setText("Sync now")
        self.clear_device_button.setEnabled(True)
        self.log(f"Sync complete · {len(pages) if hasattr(pages, '__len__') else 0} pages")
        self.load_library()

    def _sync_error(self, message: str) -> None:
        self._syncing = False
        self.sync_button.setEnabled(True)
        self.sync_button.setText("Sync now")
        self.clear_device_button.setEnabled(True)
        self.log(f"Sync failed · {message}")
        QMessageBox.warning(self, "Sync failed", f"The notebook could not be synced.\n\n{message}")

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.service.output_directory, self.service.gemini_key, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.service.save_settings(dialog.output.text().strip(), dialog.gemini.text().strip())
            self.log("Settings saved")
            self.load_library()

    def clear_device(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear notebook memory?",
            "Permanently delete every stored page from the Huion Note? Unsynced pages will be lost.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.clear_device_button.setEnabled(False)
        self.log("Clearing device memory…")
        def work() -> None:
            try:
                self.service.clear_device()
                self.clear_finished.emit()
            except Exception as exc:
                self.clear_failed.emit(str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _clear_complete(self) -> None:
        self.clear_device_button.setEnabled(True)
        self.log("Device memory cleared")
        QMessageBox.information(self, "Device cleared", "All stored pages were removed from the notebook.")

    def _clear_error(self, message: str) -> None:
        self.clear_device_button.setEnabled(True)
        self.log(f"Clear failed · {message}")
        QMessageBox.warning(self, "Clear failed", message)

    def log(self, message: str) -> None:
        self.activity.append(message)

    def closeEvent(self, event: Any) -> None:
        try:
            self.service.stop()
        finally:
            event.accept()

    @classmethod
    def run(cls, pipeline: SyncPipeline, bridge: Any) -> int:
        app = QApplication.instance() or QApplication(sys.argv)
        app.setApplicationName("HuionNote")
        app.setStyle("Fusion")
        window = cls(pipeline=pipeline, bridge=bridge)
        window.show()
        return app.exec()


def main() -> int:
    """Installed ``huionnote`` entry point."""
    from ..store import CollisionResolver, JsonStore, MarkdownStore, SvgStore
    from ..ble_bridge import DeviceBridge

    output = os.environ.get("HUION_NOTES_DIR", str(Path.home() / "HuionNotes"))
    os.makedirs(output, exist_ok=True)
    config = PipelineConfig(output_directory=output)
    registry = NoteRegistry()
    pipeline = SyncPipeline(
        config=config,
        registry=registry,
        svg_store=SvgStore(output),
        json_store=JsonStore(output),
        markdown_store=MarkdownStore(output),
        collision_resolver=CollisionResolver(output),
    )
    bridge = DeviceBridge()
    bridge.attach_pipeline(pipeline)
    return HuionNoteWindow.run(pipeline, bridge)


if __name__ == "__main__":
    raise SystemExit(main())
