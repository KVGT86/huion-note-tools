"""A quiet notes workspace with a vector notebook view for screen-sharing."""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

# Prefer native display scaling on Wayland; allow an explicit user override.
if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland;xcb")

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QIcon, QShortcut, QKeySequence, QDesktopServices
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QStackedWidget, QSplitter, QListWidget, QListWidgetItem,
    QAbstractItemView, QLineEdit, QComboBox, QTextEdit, QTextBrowser, QTabWidget,
    QDialog, QDialogButtonBox, QFormLayout, QFileDialog, QMessageBox, QCheckBox,
    QProgressBar, QMenu, QSizePolicy,
)

from huion.ink import PAGE_WIDTH, PAGE_HEIGHT, outline, svg_document
from huion.ble import load_config
from huion_note_pipeline import __version__
from huion_note_pipeline.application import HuionApplication
from huion_note_pipeline.enums import NoteStatus

INK, MUTED, PAPER, WARM, LINE = "#25231F", "#625F59", "#FFFFFF", "#F7F6F3", "#E3E1DC"
STYLE = """
QWidget { color: #25231F; font-size: 14px; }
QMainWindow, QWidget#workspace { background: #FFFFFF; }
QWidget#sidebar, QWidget#paperWell { background: #F7F6F3; }
QFrame#topbar { border-bottom: 1px solid #E3E1DC; background: #FFFFFF; }
QLabel#title { font-size: 21px; font-weight: 600; }
QLabel#brand { font-size: 17px; font-weight: 600; }
QLabel#muted { color: #625F59; font-size: 12px; }
QPushButton { border: 1px solid transparent; border-radius: 6px; padding: 7px 10px; background: transparent; }
QPushButton:hover { background: #EEEDE8; }
QPushButton:checked { background: #E8E6E1; font-weight: 600; }
QPushButton:focus { border: 1px solid #9C9A94; }
QPushButton:disabled { color: #817E78; }
QPushButton#primary { background: #25231F; color: #FFFFFF; padding: 8px 14px; }
QPushButton#primary:hover { background: #11100E; }
QPushButton#primary:disabled { background: #E8E6E1; color: #625F59; }
QLineEdit, QComboBox { background: #FFFFFF; border: 1px solid #E3E1DC; border-radius: 6px; padding: 8px; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #9C9A94; }
QListWidget { border: 0; background: #FFFFFF; }
QListWidget:focus { border: 1px solid #9C9A94; }
QListWidget::item { border-bottom: 1px solid #EEEDE8; padding: 14px 12px; }
QListWidget::item:selected { background: #EEEDE8; color: #25231F; }
QListWidget::item:hover { background: #F7F6F3; }
QTextEdit, QTextBrowser { border: 0; padding: 12px; background: #FFFFFF; selection-background-color: #E8E6E1; selection-color: #25231F; }
QTabWidget::pane { border: 0; border-top: 1px solid #E3E1DC; }
QTabBar::tab { padding: 9px 14px; background: #F7F6F3; color: #625F59; }
QTabBar::tab:selected { background: #FFFFFF; color: #25231F; }
QSplitter::handle { background: #E3E1DC; width: 1px; }
QProgressBar { border: 0; background: #EEEDE8; max-height: 3px; }
QProgressBar::chunk { background: #625F59; }
"""


def label(text: str, role: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(role)
    return widget


def button(text: str, callback: Any, primary: bool = False) -> QPushButton:
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


class PaperView(QWidget):
    """Native vector painting; zoom and pan never upscale a page bitmap."""
    zoom_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("paperWell")
        self.setMinimumSize(180, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.zoom = 1.0
        self.fit = "page"
        self.pan = QPointF()
        self._drag = None
        self.renderer = None
        self.paper_style = "Plain"

    def set_svg(self, path: str | None) -> None:
        if self.renderer is not None:
            self.renderer.deleteLater()
        self.renderer = QSvgRenderer(path, self) if path else None
        self.reset_view()
        self.update()

    def reset_view(self, mode: str = "page") -> None:
        self.fit, self.zoom, self.pan = mode, 1.0, QPointF()
        self.zoom_changed.emit("Fit page" if mode == "page" else "Fit width")
        self.update()

    def page_rect(self) -> QRectF:
        ratio = PAGE_WIDTH / PAGE_HEIGHT
        if self.renderer and self.renderer.isValid():
            box = self.renderer.viewBoxF()
            if box.height() > 0:
                ratio = box.width() / box.height()
        width = max(1, self.width() - 48)
        height = width / ratio
        if self.fit == "page" and height > self.height() - 48:
            height = max(1, self.height() - 48)
            width = height * ratio
        width, height = width * self.zoom, height * self.zoom
        y = (self.height() - height) / 2 if self.fit == "page" else 24
        return QRectF((self.width() - width) / 2 + self.pan.x(), y + self.pan.y(), width, height)

    def change_zoom(self, factor: float) -> None:
        self.zoom = min(8, max(0.25, self.zoom * factor))
        self.zoom_changed.emit(f"{self.zoom * 100:.0f}%")
        self.update()

    def wheelEvent(self, event: Any) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.change_zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        else:
            self.pan += QPointF(event.angleDelta().x() / 2, event.angleDelta().y() / 2)
            self.update()
        event.accept()

    def mousePressEvent(self, event: Any) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._drag = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: Any) -> None:
        if self._drag is not None:
            self.pan += event.position() - self._drag
            self._drag = event.position()
            self.update()

    def mouseReleaseEvent(self, event: Any) -> None:
        self._drag = None
        self.unsetCursor()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(WARM))
        page = self.page_rect()
        painter.fillRect(page, QColor(PAPER))
        painter.setPen(QPen(QColor(LINE), 1))
        painter.drawRect(page)
        painter.setClipRect(page)
        if self.renderer and self.renderer.isValid():
            self.renderer.render(painter, page)
        self.paint_ink(painter, page)

    def paint_ink(self, painter: QPainter, page: QRectF) -> None:
        pass


class LiveCanvas(PaperView):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._strokes = []
        self._active = []
        self._geometry = []
        self._dirty = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._paint_pending)
        self.timer.start(16)

    def _paint_pending(self) -> None:
        if self._dirty:
            self._dirty = False
            self.update()

    def samples(self) -> list:
        return [list(s) for s in self._strokes] + ([list(self._active)] if self._active else [])

    def set_samples(self, strokes: list) -> None:
        self._strokes = [[tuple(p) for p in s] for s in strokes if s]
        self._active = []
        self._geometry = [QPolygonF([QPointF(x, y) for x, y in outline(s)]) for s in self._strokes]
        self.update()

    def add_point(self, point: Any) -> None:
        touching = getattr(point, "touch", getattr(point, "pressure", 0) > 0)
        if touching and getattr(point, "pressure", 0) > 0:
            self._active.append((float(point.x), float(point.y), int(point.pressure)))
        elif self._active:
            self._strokes.append(self._active)
            self._geometry.append(QPolygonF([QPointF(x, y) for x, y in outline(self._active)]))
            self._active = []
        else:
            return
        self._dirty = True
        self.changed.emit()

    def clear_page(self) -> None:
        self.set_samples([])
        self.changed.emit()

    def to_svg(self) -> str:
        return svg_document(self.samples())

    def paint_ink(self, painter: QPainter, page: QRectF) -> None:
        painter.save()
        painter.translate(page.topLeft())
        painter.scale(page.width() / PAGE_WIDTH, page.height() / PAGE_HEIGHT)
        if self.paper_style != "Plain":
            painter.setPen(QPen(QColor("#D4D1CA"), 35))
            step = 1800
            for y in range(step, PAGE_HEIGHT, step):
                if self.paper_style == "Ruled":
                    painter.drawLine(QPointF(0, y), QPointF(PAGE_WIDTH, y))
                else:
                    for x in range(step, PAGE_WIDTH, step):
                        painter.drawPoint(QPointF(x, y))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(INK))
        for polygon in self._geometry:
            painter.drawPolygon(polygon)
        # ponytail: rebuild only the unfinished stroke; incremental geometry if one stroke grows very long.
        if self._active:
            painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in outline(self._active)]))
        painter.restore()


def view_controls(view: PaperView) -> QWidget:
    host = QWidget()
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    layout.addWidget(button("Fit page", lambda: view.reset_view("page")))
    layout.addWidget(button("Fit width", lambda: view.reset_view("width")))
    layout.addStretch()
    layout.addWidget(button("Zoom out", lambda: view.change_zoom(1 / 1.2)))
    value = label("Fit page", "muted")
    view.zoom_changed.connect(value.setText)
    layout.addWidget(value)
    layout.addWidget(button("Zoom in", lambda: view.change_zoom(1.2)))
    return host


class SettingsDialog(QDialog):
    def __init__(self, service: HuionApplication, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Notebook settings")
        self.setMinimumWidth(520)
        self.service = service
        form = QFormLayout(self)
        form.setContentsMargins(24, 24, 24, 24)
        self.output = QLineEdit(service.output_directory)
        self.mac = QLineEdit(service.mac_address)
        self.mac.setPlaceholderText("Automatic Bluetooth discovery")
        self.pin = QLineEdit(load_config().get("pin", ""))
        self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini = QLineEdit(service.gemini_key)
        self.gemini.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Notes folder", self.output)
        form.addRow("", button("Choose folder…", self.choose_folder))
        form.addRow("Bluetooth address", self.mac)
        form.addRow("Notebook PIN (optional)", self.pin)
        form.addRow("Gemini API key", self.gemini)
        hint = label("AI transcription sends the selected page to Google.\nLocal OCR stays on this computer.", "muted")
        hint.setWordWrap(True)
        form.addRow(hint)
        form.addRow(button("Clear stored pages from notebook…", parent.clear_device))
        self.error = label("", "muted")
        self.error.setWordWrap(True)
        form.addRow(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Notes folder", self.output.text())
        if path:
            self.output.setText(path)

    def save(self) -> None:
        try:
            self.service.save_settings(self.output.text().strip(), self.gemini.text().strip(),
                                       self.mac.text().strip(), self.pin.text().strip())
        except Exception as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class HuionNoteWindow(QMainWindow):
    pen_received = Signal(object)
    hardware_button_received = Signal()
    job_progress = Signal(int, int)
    job_done = Signal(str, object)
    job_failed = Signal(str, str)

    def __init__(self, pipeline=None, bridge=None, service=None, registry=None, config=None) -> None:
        super().__init__()
        self.service = service or HuionApplication(pipeline, bridge)
        self._busy = False
        self._draft_dirty = False
        self._presentation = False
        self._live_history = []
        self._live_paths = []
        self._history_index = 0
        self._current_live = []
        self._selected_note = None
        self._editor_dirty = False
        self.setWindowTitle("HuionNote")
        self.resize(1280, 820)
        self.setMinimumSize(860, 580)
        self.setStyleSheet(STYLE)
        icon = Path(__file__).resolve().parents[3] / "assets" / "huionnote.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self._build()
        self.pen_received.connect(self.receive_point)
        self.hardware_button_received.connect(self.new_page)
        self.service.on_pen_point(self.pen_received.emit)
        self.service.on_hardware_button(self.hardware_button_received.emit)
        self.job_progress.connect(self.show_progress)
        self.job_done.connect(self.job_complete)
        self.job_failed.connect(self.job_error)
        self.connection_timer = QTimer(self)
        self.connection_timer.timeout.connect(self.refresh_connection)
        self.connection_timer.start(1500)
        self.draft_timer = QTimer(self)
        self.draft_timer.timeout.connect(self.save_draft)
        self.draft_timer.start(3000)
        self.canvas.changed.connect(self.live_changed)
        try:
            self.canvas.set_samples(self.service.live_draft())
        except Exception as exc:
            self.log(str(exc))
        self.service.start_stream()
        self.load_library()
        self._show_page(0)
        for shortcut, callback in (
            ("F11", self.toggle_presentation), ("Escape", self.leave_presentation),
            ("Ctrl+F", self.focus_search), ("Ctrl+S", self.save_current),
            ("Ctrl+E", self.export_selected), ("Ctrl+N", self.new_page),
        ):
            key = QShortcut(QKeySequence(shortcut), self)
            key.activated.connect(callback)

    def _build(self) -> None:
        shell = QWidget()
        shell.setObjectName("workspace")
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(196)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(14, 24, 14, 18)
        side.addWidget(label("HuionNote", "brand"))
        side.addWidget(label("A place for your pages", "muted"))
        side.addSpacing(28)
        self.nav = []
        for i, title in enumerate(("Notes", "Live notebook")):
            item = button(title, lambda checked=False, n=i: self._show_page(n))
            item.setCheckable(True)
            side.addWidget(item)
            self.nav.append(item)
        side.addStretch()
        self.device_label = label("Connecting to notebook…", "muted")
        self.device_label.setWordWrap(True)
        self.device_label.setMinimumHeight(44)
        side.addWidget(self.device_label)
        side.addWidget(button("Reconnect", self.retry_connection))
        side.addSpacing(16)
        side.addWidget(button("Activity", lambda: self.activity.setVisible(not self.activity.isVisible())))
        side.addWidget(button("Settings", self.open_settings))
        side.addWidget(label(f"HuionNote {__version__}", "muted"))
        root.addWidget(self.sidebar)
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.topbar = QFrame()
        self.topbar.setObjectName("topbar")
        bar = QHBoxLayout(self.topbar)
        bar.setContentsMargins(24, 16, 24, 16)
        self.page_title = label("Notes", "title")
        bar.addWidget(self.page_title)
        bar.addStretch()
        self.top_status = label("Connecting", "muted")
        bar.addWidget(self.top_status)
        self.sync_button = button("Sync notebook", self.sync_now, True)
        bar.addWidget(self.sync_button)
        column.addWidget(self.topbar)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        column.addWidget(self.progress)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.library_page())
        self.pages.addWidget(self.live_page())
        column.addWidget(self.pages, 1)
        self.activity = QTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumHeight(110)
        self.activity.hide()
        column.addWidget(self.activity)
        self.footer = label("Your original pages stay on the notebook after sync.", "muted")
        self.footer.setContentsMargins(24, 8, 24, 8)
        column.addWidget(self.footer)
        root.addWidget(content, 1)
        self.setCentralWidget(shell)

    def library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 18, 24, 0)
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search titles and transcripts")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_notes)
        controls.addWidget(self.search, 1)
        self.filter = QComboBox()
        self.filter.addItems(["All pages", "Needs transcription", "Transcribed", "Needs attention"])
        self.filter.currentIndexChanged.connect(self.refresh_notes)
        controls.addWidget(self.filter)
        controls.addWidget(button("Refresh", self.load_library))
        layout.addLayout(controls)
        self.splitter = QSplitter()
        left = QWidget()
        list_layout = QVBoxLayout(left)
        list_layout.setContentsMargins(0, 8, 12, 0)
        self.library_count = label("0 pages", "muted")
        list_layout.addWidget(self.library_count)
        self.note_list = QListWidget()
        self.note_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.note_list.setWordWrap(True)
        self.note_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.note_list.itemSelectionChanged.connect(self.selection_changed)
        self.note_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.note_list.customContextMenuRequested.connect(self.note_menu)
        list_layout.addWidget(self.note_list, 1)
        self.empty_list = label("Sync your notebook to bring pages here.", "muted")
        self.empty_list.setWordWrap(True)
        list_layout.addWidget(self.empty_list)
        actions = QHBoxLayout()
        self.export_button = button("Export…", self.export_selected)
        self.transcribe_button = button("Transcribe…", self.transcribe_selected)
        actions.addWidget(self.export_button)
        actions.addWidget(self.transcribe_button)
        list_layout.addLayout(actions)
        self.splitter.addWidget(left)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(16, 8, 0, 0)
        self.note_title = label("Your pages, ready to read", "title")
        self.note_title.setWordWrap(True)
        detail_layout.addWidget(self.note_title)
        self.note_meta = label("Select a page to view handwriting and its transcript.", "muted")
        self.note_meta.setWordWrap(True)
        detail_layout.addWidget(self.note_meta)
        self.preview = PaperView()
        self.preview_controls = view_controls(self.preview)
        detail_layout.addWidget(self.preview_controls)
        self.detail_tabs = QTabWidget()
        self.detail_tabs.addTab(self.preview, "Handwriting")
        self.reader = QTextBrowser()
        self.reader.setOpenExternalLinks(False)
        self.reader.anchorClicked.connect(self.open_transcript_link)
        self.detail_tabs.addTab(self.reader, "Transcript")
        review = QWidget()
        review_layout = QVBoxLayout(review)
        review_layout.setContentsMargins(0, 0, 0, 0)
        self.review_splitter = QSplitter()
        self.review_preview = PaperView()
        self.review_preview.setMinimumSize(120, 120)
        review_layout.addWidget(view_controls(self.review_preview))
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setEnabled(False)
        self.editor.setPlaceholderText("Review your transcript here, or write one yourself. Choose Transcribe to start from the handwriting.")
        self.editor.textChanged.connect(self.editor_changed)
        self.review_splitter.addWidget(self.review_preview)
        self.review_splitter.addWidget(self.editor)
        self.review_splitter.setChildrenCollapsible(False)
        self.review_splitter.setSizes([400, 400])
        review_layout.addWidget(self.review_splitter, 1)
        review_layout.addWidget(button("Save transcript", self.save_transcript), alignment=Qt.AlignmentFlag.AlignRight)
        self.detail_tabs.addTab(review, "Review && edit")
        self.detail_tabs.currentChanged.connect(self.active_preview_changed)
        detail_layout.addWidget(self.detail_tabs, 1)
        self.splitter.addWidget(detail)
        self.splitter.setSizes([300, 700])
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        layout.addWidget(self.splitter, 1)
        return page

    def live_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 12, 24, 12)
        self.live_toolbar = QWidget()
        tools = QHBoxLayout(self.live_toolbar)
        tools.setContentsMargins(0, 0, 0, 0)
        self.live_position = label("Current page", "muted")
        tools.addWidget(button("Previous", lambda: self.browse_live(-1)))
        tools.addWidget(self.live_position)
        tools.addWidget(button("Next", lambda: self.browse_live(1)))
        tools.addStretch()
        tools.addWidget(button("Save page", self.save_live))
        tools.addWidget(button("New page", self.new_page))
        tools.addWidget(button("Present · F11", self.toggle_presentation))
        layout.addWidget(self.live_toolbar)
        self.canvas = LiveCanvas()
        self.live_view_controls = view_controls(self.canvas)
        control_layout = self.live_view_controls.layout()
        self.paper_choice = QComboBox()
        self.paper_choice.addItems(["Plain", "Ruled", "Dotted"])
        self.paper_choice.currentTextChanged.connect(self.change_paper)
        control_layout.insertWidget(0, self.paper_choice)
        layout.addWidget(self.live_view_controls)
        layout.addWidget(self.canvas, 1)
        self.live_hint = label("Write on the X10. Pages are recoverable locally. Ctrl+wheel to zoom; drag to pan.", "muted")
        layout.addWidget(self.live_hint)
        return page

    def change_paper(self, style: str) -> None:
        self.canvas.paper_style = style
        self.canvas.update()

    def _show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.page_title.setText("Notes" if index == 0 else "Live notebook")
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)

    def focus_search(self) -> None:
        self.leave_presentation()
        self._show_page(0)
        self.search.setFocus()

    def refresh_connection(self) -> None:
        snapshot = self.service.device_snapshot()
        if snapshot.connected is True:
            self.top_status.setText("Connected")
            self.device_label.setText("Huion Note X10" + (f" · {snapshot.battery}%" if snapshot.battery is not None else ""))
        elif snapshot.connected is None:
            self.top_status.setText("Connecting")
            self.device_label.setText("Wake the X10 with your pen.")
        else:
            self.top_status.setText("Offline")
            self.device_label.setText("Notebook offline. Saved pages are available.")

    def retry_connection(self) -> None:
        if not self._busy:
            threading.Thread(target=self.service.retry_connection, daemon=True).start()
            self.log("Reconnecting to notebook…")

    def load_library(self) -> None:
        try:
            self._all_notes = self.service.load_notes()
            self._search_text = {}
            for note in self._all_notes:
                text = Path(note.svg_path).stem.replace("_", " ")
                if note.markdown_path and Path(note.markdown_path).exists():
                    text += " " + Path(note.markdown_path).read_text(encoding="utf-8")
                self._search_text[note.svg_path] = text.casefold()
            self.refresh_notes()
        except Exception as exc:
            self.log(f"Could not read notes: {exc}")

    def refresh_notes(self, *args: Any) -> None:
        if not hasattr(self, "_all_notes"):
            return
        selected = {n.svg_path for n in self.selected_notes()}
        self.note_list.blockSignals(True)
        self.note_list.clear()
        term = self.search.text().strip().casefold()
        filter_index = self.filter.currentIndex()
        for note in self._all_notes:
            if term and term not in self._search_text.get(note.svg_path, ""):
                continue
            if filter_index == 1 and note.status not in (NoteStatus.SYNCED, NoteStatus.CONVERTING):
                continue
            if filter_index == 2 and note.status != NoteStatus.CONVERTED:
                continue
            if filter_index == 3 and note.status != NoteStatus.FAILED:
                continue
            title = Path(note.svg_path).stem.replace("_", " ").title()
            status = {NoteStatus.SYNCED: "Ready", NoteStatus.CONVERTING: "Transcribing",
                      NoteStatus.CONVERTED: "Transcribed", NoteStatus.FAILED: "Needs attention"}[note.status]
            item = QListWidgetItem(f"{title}\n{note.synced_at:%d %b %Y} · {status}")
            item.setToolTip(f"{title}\n{note.synced_at:%d %b %Y} · {status}")
            item.setData(Qt.ItemDataRole.UserRole, note)
            self.note_list.addItem(item)
            if note.svg_path in selected:
                item.setSelected(True)
        self.note_list.blockSignals(False)
        count = self.note_list.count()
        self.library_count.setText(f"{count} page{'s' if count != 1 else ''}")
        self.empty_list.setVisible(count == 0)
        self.empty_list.setText("No matching pages. Try another search or filter." if self._all_notes else "Sync your notebook to bring pages here.")
        self.selection_changed()

    def selected_notes(self) -> list:
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.note_list.selectedItems()]

    def selection_changed(self) -> None:
        notes = self.selected_notes()
        self.export_button.setEnabled(bool(notes) and not self._busy)
        self.transcribe_button.setEnabled(bool(notes) and not self._busy)
        if not notes:
            return
        note = notes[0]
        if self._selected_note and self._selected_note.svg_path == note.svg_path:
            return
        if not self.resolve_editor():
            self.note_list.blockSignals(True)
            self.note_list.clearSelection()
            for i in range(self.note_list.count()):
                item = self.note_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole).svg_path == self._selected_note.svg_path:
                    item.setSelected(True)
            self.note_list.blockSignals(False)
            return
        self._selected_note = note
        self.editor.setEnabled(True)
        self.note_title.setText(Path(note.svg_path).stem.replace("_", " ").title())
        self.note_meta.setText(f"{note.synced_at:%d %B %Y, %H:%M} · {len(notes)} selected" if len(notes) > 1 else f"{note.synced_at:%d %B %Y, %H:%M}")
        self.preview.set_svg(note.svg_path)
        self.review_preview.set_svg(note.svg_path)
        markdown = Path(note.markdown_path).read_text(encoding="utf-8") if note.markdown_path and Path(note.markdown_path).exists() else ""
        self.reader.document().setBaseUrl(QUrl.fromLocalFile(str(Path(note.svg_path).parent) + "/"))
        self.reader.setMarkdown(markdown or "No transcript yet.\n\nChoose **Transcribe** for local OCR or AI transcription.")
        self.editor.setPlainText(markdown)
        self._editor_dirty = False

    def open_transcript_link(self, url: QUrl) -> None:
        if url.scheme() in ("https", "http"):
            QDesktopServices.openUrl(url)

    def active_preview_changed(self, index: int) -> None:
        self.preview_controls.setVisible(index == 0)
        if index == 2:
            QTimer.singleShot(0, self.adapt_review)

    def adapt_review(self) -> None:
        orientation = Qt.Orientation.Vertical if self.review_splitter.width() < 600 else Qt.Orientation.Horizontal
        if self.review_splitter.orientation() != orientation:
            self.review_splitter.setOrientation(orientation)
            self.review_splitter.setSizes([400, 400])

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if hasattr(self, "review_splitter"):
            QTimer.singleShot(0, self.adapt_review)

    def editor_changed(self) -> None:
        self._editor_dirty = True

    def save_transcript(self) -> bool:
        if not self._selected_note:
            return True
        try:
            self.service.save_markdown(self._selected_note, self.editor.toPlainText())
            self._editor_dirty = False
            self.reader.setMarkdown(self.editor.toPlainText())
            self.log("Transcript saved.")
            self.load_library()
            return True
        except Exception as exc:
            QMessageBox.warning(self, "Transcript could not be saved", str(exc))
            return False

    def resolve_editor(self) -> bool:
        if not self._editor_dirty:
            return True
        answer = QMessageBox.question(self, "Save transcript changes?", "Save your edits before leaving this page?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save_transcript()
        self._editor_dirty = False
        return True

    def note_menu(self, position: Any) -> None:
        if not self.selected_notes():
            return
        menu = QMenu(self)
        menu.addAction("Export selected pages…", self.export_selected)
        menu.addAction("Transcribe selected pages…", self.transcribe_selected)
        menu.addAction("Open original in default app", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.selected_notes()[0].svg_path)))
        menu.exec(self.note_list.mapToGlobal(position))

    def run_job(self, name: str, work: Any) -> None:
        if self._busy:
            return
        self._busy = True
        self.sync_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.transcribe_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.log(f"{name}…")
        def worker() -> None:
            try:
                self.job_done.emit(name, work())
            except Exception as exc:
                self.job_failed.emit(name, str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def show_progress(self, current: int, total: int) -> None:
        if total == 0:
            self.progress.setRange(0, 0)
            self.footer.setText(f"Syncing notebook · {current} pages saved")
            return
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(current)
        self.footer.setText(f"{current} of {total} pages processed")

    def finish_job(self) -> None:
        self._busy = False
        self.progress.hide()
        self.sync_button.setEnabled(True)
        self.export_button.setEnabled(bool(self.selected_notes()))
        self.transcribe_button.setEnabled(bool(self.selected_notes()))

    def job_complete(self, name: str, result: Any) -> None:
        self.finish_job()
        count = len(result) if isinstance(result, list) else 0
        self.log(f"{name} complete · {count} file{'s' if count != 1 else ''}" if name == "Export" else f"{name} complete.")
        self.load_library()
        if name == "Transcription" and self._selected_note and not self._editor_dirty:
            self._selected_note = None
            self.selection_changed()
        if name == "Sync":
            self._show_page(0)
            self.log(f"Synced {count} pages. Originals remain on the notebook.")

    def job_error(self, name: str, message: str) -> None:
        self.finish_job()
        self.load_library()
        if name == "Transcription" and self._selected_note and not self._editor_dirty:
            self._selected_note = None
            self.selection_changed()
        self.log(f"{name} failed: {message}")
        QMessageBox.warning(self, f"{name} could not finish", message)

    def sync_now(self) -> None:
        self.run_job("Sync", lambda: self.service.sync(progress=self.job_progress.emit))

    def export_selected(self) -> None:
        notes = self.selected_notes()
        if self.pages.currentIndex() == 1:
            if not self.save_live():
                return
            notes = [n for n in self.service.load_notes() if n.svg_path == self._last_live_path]
        if not notes or self._busy:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Export pages")
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(f"Export {len(notes)} selected page{'s' if len(notes) != 1 else ''}", "title"))
        checks = {}
        for fmt, name in (("svg", "SVG · vector handwriting"), ("pdf", "PDF · share or print"),
                          ("png", "PNG · high-resolution image"), ("json", "JSON · original pen samples"),
                          ("md", "Markdown · transcript and sketch")):
            check = QCheckBox(name)
            check.setChecked(fmt == "pdf")
            if fmt in ("json", "md"):
                check.setEnabled(any((n.json_path and Path(n.json_path).suffix == ".json") if fmt == "json" else n.markdown_path for n in notes))
            checks[fmt] = check
            layout.addWidget(check)
        layout.addWidget(label("Existing files are kept. Only available transcripts and raw data are exported.", "muted"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        formats = [fmt for fmt, check in checks.items() if check.isChecked()]
        if not formats:
            return
        directory = QFileDialog.getExistingDirectory(self, "Export destination")
        if directory:
            self.run_job("Export", lambda: self.service.export_notes(notes, directory, formats, self.job_progress.emit))

    def transcribe_selected(self) -> None:
        notes = [n for n in self.selected_notes() if n.status in (NoteStatus.SYNCED, NoteStatus.FAILED)]
        if not notes or self._busy:
            if not self._busy:
                self.log("These pages already have transcripts. Open Review & edit to make changes.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Transcribe handwriting")
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(f"Transcribe {len(notes)} page{'s' if len(notes) != 1 else ''}", "title"))
        method = QComboBox()
        method.addItems(["Local OCR · stays on this computer", "AI · sends selected pages to Google Gemini"])
        layout.addWidget(method)
        hint = label("Local OCR requires Tesseract. AI requires a Gemini API key in Settings.", "muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        cloud = method.currentIndex() == 1
        if cloud and not self.service.gemini_key:
            QMessageBox.information(self, "Add a Gemini key", "Add your Gemini API key in Settings, then try again.")
            return
        def work() -> list:
            failures = []
            for index, note in enumerate(notes):
                try:
                    self.service.convert(note, cloud=cloud)
                except Exception as exc:
                    failures.append(f"{Path(note.svg_path).name}: {exc}")
                self.job_progress.emit(index + 1, len(notes))
            if failures:
                raise RuntimeError("Some pages could not be transcribed. Successful pages were saved.\n\n" + "\n".join(failures))
            return notes
        self.run_job("Transcription", work)

    def receive_point(self, point: Any) -> None:
        if self._history_index < len(self._live_history):
            self._history_index = len(self._live_history)
            self.canvas.set_samples(self._current_live)
            self.live_position.setText("Current page")
        self.canvas.add_point(point)

    def live_changed(self) -> None:
        self._draft_dirty = True

    def save_draft(self) -> bool:
        if self._history_index < len(self._live_history):
            return True
        if not self._draft_dirty:
            return True
        try:
            self.service.save_live_draft(self.canvas.samples())
            self._draft_dirty = False
            return True
        except Exception as exc:
            self.log(f"Live page could not be saved: {exc}. Export or check the notes folder.")
            return False

    def save_live(self) -> bool:
        if self._history_index < len(self._live_history):
            self._last_live_path = self._live_paths[self._history_index]
            return True
        if not self.canvas.samples():
            self.log("Write on the notebook before saving a page.")
            return False
        try:
            self._last_live_path = self.service.save_live_page(self.canvas.samples())
            self._draft_dirty = False
            self.log("Live page saved to Notes.")
            self.load_library()
            return True
        except Exception as exc:
            QMessageBox.warning(self, "Page could not be saved", str(exc))
            return False

    def new_page(self) -> None:
        if self._history_index < len(self._live_history):
            self.browse_live(len(self._live_history) - self._history_index)
        if self.canvas.samples():
            if not self.save_live():
                return
            self._live_history.append(self.canvas.samples())
            self._live_paths.append(self._last_live_path)
        try:
            self.service.new_live_page()
        except Exception as exc:
            self.log(f"Could not start a new page: {exc}")
            return
        self.canvas.set_samples([])
        self._history_index = len(self._live_history)
        self._current_live = []
        self._draft_dirty = False
        self.live_position.setText("Current page")
        self.canvas.reset_view()

    def browse_live(self, direction: int) -> None:
        target = max(0, min(len(self._live_history), self._history_index + direction))
        if target == self._history_index:
            return
        if self._history_index == len(self._live_history):
            if not self.save_draft():
                return
            self._current_live = self.canvas.samples()
        self._history_index = target
        self.canvas.set_samples(self._current_live if target == len(self._live_history) else self._live_history[target])
        self.live_position.setText("Current page" if target == len(self._live_history) else f"Saved page {target + 1}")
        self.canvas.reset_view()

    def toggle_presentation(self) -> None:
        if self._presentation:
            self.leave_presentation()
            return
        self._show_page(1)
        self._was_maximized = self.isMaximized()
        self._presentation = True
        for widget in (self.sidebar, self.topbar, self.live_toolbar, self.live_view_controls, self.live_hint, self.footer, self.activity, self.progress):
            widget.hide()
        self.showFullScreen()
        self.canvas.reset_view()

    def leave_presentation(self) -> None:
        if not self._presentation:
            return
        self._presentation = False
        for widget in (self.sidebar, self.topbar, self.live_toolbar, self.live_view_controls, self.live_hint, self.footer):
            widget.show()
        if self._busy:
            self.progress.show()
        self.showMaximized() if self._was_maximized else self.showNormal()

    def save_current(self) -> None:
        self.save_live() if self.pages.currentIndex() == 1 else self.save_transcript()

    def open_settings(self) -> None:
        if self._busy:
            self.log("Wait for the current operation to finish before changing settings.")
            return
        if not self.save_draft():
            return
        dialog = SettingsDialog(self.service, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._draft_dirty = bool(self.canvas.samples())
            self.save_draft()
            self.load_library()
            self.retry_connection()
            self.log("Settings saved.")

    def clear_device(self) -> None:
        if self._busy:
            return
        answer = QMessageBox.question(self, "Clear notebook memory?",
            "This permanently removes every stored page from the X10.\n\nSaved local pages stay on this computer. Unsynced pages will be lost. Sync and check your saved pages first.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Yes:
            self.run_job("Clear notebook memory", self.service.clear_device)

    def log(self, message: str) -> None:
        self.activity.append(message)
        self.footer.setText(message)

    def closeEvent(self, event: Any) -> None:
        if self._busy:
            QMessageBox.information(self, "Operation in progress", "Let the current operation finish before closing HuionNote.")
            event.ignore()
            return
        if not self.resolve_editor():
            event.ignore()
            return
        if self._history_index < len(self._live_history):
            self.canvas.set_samples(self._current_live)
            self._history_index = len(self._live_history)
        self._draft_dirty = True
        if not self.save_draft():
            QMessageBox.warning(self, "Live draft could not be saved", "Check the notes folder or export the page before closing.")
            event.ignore()
            return
        self.service.stop()
        event.accept()

    @classmethod
    def run(cls, pipeline=None, bridge=None, service=None) -> int:
        app = QApplication.instance() or QApplication(sys.argv)
        app.setApplicationName("huionnote")
        app.setApplicationDisplayName("HuionNote")
        app.setDesktopFileName("huionnote")
        window = cls(pipeline, bridge, service=service)
        window.show()
        return app.exec()


def main() -> int:
    from huion_note_pipeline.application import create_application
    return HuionNoteWindow.run(service=create_application())
