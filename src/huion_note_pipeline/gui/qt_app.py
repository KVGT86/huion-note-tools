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

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal, QUrl, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QIcon, QShortcut, QKeySequence, QDesktopServices, QPalette, QFont, QPixmap, QImage
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QStackedWidget, QSplitter, QListWidget, QListWidgetItem,
    QAbstractItemView, QLineEdit, QComboBox, QTextEdit, QTextBrowser, QTabWidget,
    QDialog, QDialogButtonBox, QFormLayout, QFileDialog, QMessageBox, QCheckBox,
    QProgressBar, QMenu, QSizePolicy, QStyledItemDelegate, QListView, QToolButton, QStatusBar, QColorDialog,
    QInputDialog, QGroupBox,
)

from huion.ink import PAGE_WIDTH, PAGE_HEIGHT, outline, svg_document, stroke_colors, validate_color, fit_image_rect
from huion.ble import load_config
from huion_note_pipeline import __version__
from huion_note_pipeline.application import HuionApplication
from huion_note_pipeline.enums import NoteStatus

INK, MUTED, PAPER, WARM, LINE = "#25231F", "#625F59", "#FFFFFF", "#F2F1ED", "#D6D3CC"
ASSETS = Path(__file__).resolve().parents[3] / "assets"
ICONS = Path(__file__).resolve().parent / "icons" / "lucide"
STYLE = """
QWidget { color: #25231F; font-size: 14px; }
QMainWindow, QWidget#workspace { background: #FFFFFF; }
QDialog { background: #FFFFFF; }
QWidget#sidebar, QWidget#paperWell { background: #F2F1ED; }
QWidget#sidebar { border-right: 1px solid #D6D3CC; }
QFrame#topbar { border-bottom: 1px solid #D6D3CC; background: #FFFFFF; }
QStatusBar { background: #F2F1ED; border-top: 1px solid #D6D3CC; }
QStatusBar::item { border: 0; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 5px; padding: 6px; }
QToolButton:hover { background: #E4E1DA; }
QToolButton:pressed, QToolButton:checked { background: #DCEAF2; border-color: #B8B3AA; }
QToolButton:focus { border-color: #35698F; }
QToolButton#utility { text-align: left; padding: 9px 10px; }
QToolButton#inkChoice { padding-right: 18px; }
QToolButton#inkChoice::menu-indicator { image: url(__CHEVRON__); width: 12px; height: 12px; subcontrol-position: right center; right: 3px; }
QFrame#toolDivider { background: #D6D3CC; max-width: 1px; }
QComboBox#paperChoice { min-width: 64px; }
QLabel#title { font-size: 21px; font-weight: 600; }
QLabel#brand { font-size: 17px; font-weight: 600; }
QLabel#muted { color: #625F59; font-size: 13px; }
QLabel#empty { color: #625F59; padding: 24px; background: #F2F1ED; }
QLabel#metric { font-size: 28px; font-weight: 600; }
QGroupBox { border: 1px solid #D6D3CC; border-radius: 6px; margin-top: 12px; padding: 18px 16px 16px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QPushButton { border: 1px solid #D6D3CC; border-radius: 6px; padding: 8px 12px; background: #FFFFFF; }
QPushButton:hover { background: #EEECE6; border-color: #A6A198; }
QPushButton:pressed { background: #DEDAD2; }
QPushButton:checked { background: #25231F; color: #FFFFFF; font-weight: 600; border-color: #25231F; }
QPushButton:focus { border: 2px solid #35698F; padding: 7px 11px; }
QPushButton:disabled { color: #817E78; }
QPushButton#quiet { background: transparent; border-color: transparent; }
QPushButton#quiet:hover { background: #E4E1DA; }
QPushButton#quiet:focus { border-color: #35698F; }
QPushButton#nav { text-align: left; border-color: transparent; background: transparent; padding: 10px 12px; }
QPushButton#nav:hover { background: #E4E1DA; }
QPushButton#nav:checked { background: #25231F; color: #FFFFFF; }
QPushButton#nav:focus { border-color: #35698F; }
QPushButton#primary { background: #25231F; color: #FFFFFF; padding: 8px 14px; }
QPushButton#primary:hover { background: #11100E; }
QPushButton#primary:disabled { background: #E4E1DA; color: #625F59; }
QPushButton#danger { color: #912D27; border-color: #D6B6B1; }
QPushButton#danger:hover { background: #FAEDEB; }
QLineEdit, QComboBox { background: #FFFFFF; border: 1px solid #B8B3AA; border-radius: 6px; padding: 9px 12px; selection-background-color: #DCEAF2; selection-color: #25231F; }
QLineEdit, QTextEdit { placeholder-text-color: #625F59; }
QLineEdit:hover, QComboBox:hover { border-color: #81796B; }
QLineEdit:focus, QComboBox:focus { border: 2px solid #35698F; padding: 8px 11px; }
QComboBox { padding-right: 36px; min-width: 112px; }
QComboBox:focus { padding-right: 35px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 30px; border: 0; }
QComboBox::down-arrow { image: url(__CHEVRON__); width: 14px; height: 14px; }
QComboBox QAbstractItemView { background: #FFFFFF; color: #25231F; border: 1px solid #A6A198; padding: 5px; outline: 0; selection-background-color: #DCEAF2; selection-color: #25231F; }
QComboBox QAbstractItemView::item { min-height: 32px; padding: 4px 10px; border: 0; border-radius: 4px; }
QComboBox QAbstractItemView::item:hover { background: #EEECE6; }
QComboBox QAbstractItemView::item:selected { background: #DCEAF2; color: #25231F; }
QListWidget { border: 1px solid transparent; background: #FFFFFF; }
QListWidget:focus { border: 1px solid #35698F; }
QTextEdit, QTextBrowser { border: 0; padding: 16px; background: #FFFFFF; selection-background-color: #DCEAF2; selection-color: #25231F; }
QTabWidget::pane { border: 0; border-top: 1px solid #D6D3CC; }
QTabBar::tab { padding: 11px 14px; background: #FFFFFF; color: #625F59; border-bottom: 2px solid transparent; }
QTabBar::tab:hover { background: #F2F1ED; color: #25231F; }
QTabBar::tab:selected { border-bottom: 2px solid #25231F; color: #25231F; font-weight: 600; }
QSplitter::handle { background: #D6D3CC; width: 1px; }
QCheckBox { spacing: 10px; padding: 8px 0; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #81796B; border-radius: 4px; background: #FFFFFF; }
QCheckBox::indicator:checked { background: #25231F; border-color: #25231F; image: url(__CHECK__); }
QCheckBox:focus { color: #315D78; }
QCheckBox:disabled { color: #817E78; }
QMenu { background: #FFFFFF; border: 1px solid #B8B3AA; padding: 6px; }
QMenu::item { padding: 9px 16px; border-radius: 4px; }
QMenu::item:selected { background: #DCEAF2; color: #25231F; }
QScrollBar:vertical { background: #F2F1ED; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #B8B3AA; min-height: 28px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: #81796B; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar { border: 0; background: #E4E1DA; max-height: 3px; }
QProgressBar::chunk { background: #4682B4; }
""".replace("__CHEVRON__", (ICONS / "chevron-down.svg").as_posix()).replace("__CHECK__", (ICONS / "check-white.svg").as_posix())


def label(text: str, role: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(role)
    return widget


def button(text: str, callback: Any, primary: bool = False, role: str = "") -> QPushButton:
    widget = QPushButton(text)
    widget.setObjectName("primary" if primary else role)
    widget.clicked.connect(callback)
    return widget


def combo_box(items: list[str], name: str) -> QComboBox:
    widget = QComboBox()
    widget.setView(QListView())
    widget.addItems(items)
    widget.setAccessibleName(name)
    return widget


# Original Lucide SVGs; source revision and license are bundled beside them.
ICON_NAMES = {
    "save": "save", "new": "file-plus", "present": "monitor",
    "fit-page": "maximize", "fit-width": "move-horizontal",
    "minus": "minus", "plus": "plus", "previous": "chevron-left",
    "next": "chevron-right", "reconnect": "refresh-cw", "activity": "list",
    "settings": "settings", "bluetooth": "bluetooth", "delete": "trash", "color": "palette",
    "image": "image-plus",
    "device": "hard-drive-download", "undo": "undo-2", "redo": "redo-2", "eraser": "eraser",
    "highlighter": "highlighter", "organize": "tags", "rotate": "rotate-cw",
    "crop": "crop", "opacity": "contrast", "pointer": "mouse-pointer-2",
}


def ui_icon(name: str) -> QIcon:
    return QIcon(str(ICONS / f"{ICON_NAMES[name]}.svg"))


def tool_button(icon: str, name: str, callback: Any, text: str = "") -> QToolButton:
    widget = QToolButton()
    widget.setIcon(ui_icon(icon))
    widget.setIconSize(QSize(18, 18))
    widget.setAccessibleName(name)
    widget.setToolTip(name)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setMinimumSize(32, 32)
    if text:
        widget.setText(text)
        widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    widget.clicked.connect(callback)
    return widget


def tool_divider() -> QFrame:
    widget = QFrame()
    widget.setObjectName("toolDivider")
    widget.setFixedSize(1, 20)
    return widget


class NoteDelegate(QStyledItemDelegate):
    """Native list interactions with a readable title/metadata hierarchy."""

    def sizeHint(self, option, index) -> QSize:
        return QSize(200, 82)

    def paint(self, painter, option, index) -> None:
        from PySide6.QtWidgets import QStyle
        painter.save()
        rect = option.rect.adjusted(4, 4, -10, -4)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#DCEAF2" if selected else WARM if hovered else PAPER))
        painter.setPen(QPen(QColor("#35698F" if option.state & QStyle.StateFlag.State_HasFocus else LINE), 1)
                       if selected else Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(rect), 6, 6)
        title, _, meta = index.data().partition("\n")
        font = option.font
        font.setPixelSize(14)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(INK))
        painter.drawText(rect.adjusted(12, 13, -12, -36), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, rect.width() - 24))
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor("#2F5368" if selected else MUTED))
        painter.drawText(rect.adjusted(12, 39, -12, -10), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(meta, Qt.TextElideMode.ElideRight, rect.width() - 24))
        painter.restore()


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
        self.paint_background(painter, page)
        self.paint_ink(painter, page)

    def paint_background(self, painter: QPainter, page: QRectF) -> None:
        pass

    def paint_ink(self, painter: QPainter, page: QRectF) -> None:
        pass


class LiveCanvas(PaperView):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._strokes = []
        self._active = []
        self._geometry = []
        self._colors = []
        self.ink_color = INK
        self._active_color = INK
        self._background = QImage()
        self._dirty = False
        self._redo = []
        self.tool = "ink"
        self._pointer = None
        self._erasing = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._paint_pending)
        self.timer.start(16)

    def _paint_pending(self) -> None:
        if self._dirty:
            self._dirty = False
            self.update()

    def samples(self) -> list:
        return [list(s) for s in self._strokes] + ([list(self._active)] if self._active else [])

    def colors(self) -> list[str]:
        return list(self._colors) + ([self._active_color] if self._active else [])

    def can_undo(self) -> bool:
        return bool(self._active or self._strokes)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def set_ink_color(self, color: str) -> None:
        self.ink_color = validate_color(color)
        self.changed.emit()

    def set_tool(self, tool: str) -> None:
        if tool not in {"ink", "highlighter", "eraser", "pointer"}:
            raise ValueError(f"Unsupported live tool: {tool}")
        self.tool = tool
        self._active = []
        self._pointer = None
        self.update()

    def undo(self) -> None:
        if self._active:
            self._active = []
        elif self._strokes:
            self._redo.append((self._strokes.pop(), self._colors.pop()))
            self._geometry.pop()
        else:
            return
        self.changed.emit()
        self.update()

    def redo(self) -> None:
        if not self._redo:
            return
        stroke, color = self._redo.pop()
        self._strokes.append(stroke)
        self._colors.append(color)
        self._geometry.append(QPolygonF([QPointF(x, y) for x, y in outline(stroke)]))
        self.changed.emit()
        self.update()

    def set_samples(self, strokes: list, colors: list[str] | None = None) -> None:
        colors = stroke_colors(len(strokes), colors)
        self._strokes = [[tuple(p) for p in s] for s in strokes if s]
        self._colors = [c for s, c in zip(strokes, colors) if s]
        self._active = []
        self._redo = []
        self._geometry = [QPolygonF([QPointF(x, y) for x, y in outline(s)]) for s in self._strokes]
        self.update()

    def set_background(self, source: str | QImage | None) -> None:
        image = QImage(source) if source is not None else QImage()
        if source is not None and image.isNull():
            raise ValueError("The page image could not be displayed.")
        self._background = image
        self.update()

    def background_image(self) -> QImage | None:
        return QImage(self._background) if not self._background.isNull() else None

    def has_background(self) -> bool:
        return not self._background.isNull()

    def add_point(self, point: Any) -> None:
        touching = getattr(point, "touch", getattr(point, "pressure", 0) > 0)
        if self.tool == "pointer":
            self._pointer = QPointF(float(point.x), float(point.y)) if touching else None
            self._dirty = True
            return
        if self.tool == "eraser":
            if touching and not self._erasing and self._strokes:
                x, y = float(point.x), float(point.y)
                index, distance = min(
                    ((i, min((px - x) ** 2 + (py - y) ** 2 for px, py, _ in stroke))
                     for i, stroke in enumerate(self._strokes)), key=lambda value: value[1])
                if distance <= 1600 ** 2:
                    self._redo.append((self._strokes.pop(index), self._colors.pop(index)))
                    self._geometry.pop(index)
                    self.changed.emit()
                self._erasing = True
            elif not touching:
                self._erasing = False
            self._dirty = True
            return
        if touching and getattr(point, "pressure", 0) > 0:
            if not self._active:
                self._active_color = "#D7B43C" if self.tool == "highlighter" else self.ink_color
                self._redo = []
            self._active.append((float(point.x), float(point.y), int(point.pressure)))
        elif self._active:
            self._strokes.append(self._active)
            self._colors.append(self._active_color)
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
        return svg_document(self.samples(), self.colors())

    def paint_background(self, painter: QPainter, page: QRectF) -> None:
        if self._background.isNull():
            return
        x, y, width, height = fit_image_rect(self._background.width(), self._background.height())
        painter.save()
        painter.translate(page.topLeft())
        painter.scale(page.width() / PAGE_WIDTH, page.height() / PAGE_HEIGHT)
        painter.drawImage(QRectF(x, y, width, height), self._background)
        painter.restore()

    def paint_ink(self, painter: QPainter, page: QRectF) -> None:
        painter.save()
        painter.translate(page.topLeft())
        painter.scale(page.width() / PAGE_WIDTH, page.height() / PAGE_HEIGHT)
        if self.paper_style != "Plain":
            painter.setPen(QPen(QColor("#D4D1CA"), 35))
            step = 1800
            for y in range(step, PAGE_HEIGHT, step):
                if self.paper_style in {"Ruled", "Grid"}:
                    painter.drawLine(QPointF(0, y), QPointF(PAGE_WIDTH, y))
                else:
                    for x in range(step, PAGE_WIDTH, step):
                        painter.drawPoint(QPointF(x, y))
            if self.paper_style == "Grid":
                for x in range(step, PAGE_WIDTH, step):
                    painter.drawLine(QPointF(x, 0), QPointF(x, PAGE_HEIGHT))
        painter.setPen(Qt.PenStyle.NoPen)
        for polygon, color in zip(self._geometry, self._colors):
            painter.setBrush(QColor(color))
            painter.drawPolygon(polygon, Qt.FillRule.WindingFill)
        # ponytail: rebuild only the unfinished stroke; incremental geometry if one stroke grows very long.
        if self._active:
            painter.setBrush(QColor(self._active_color))
            painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in outline(self._active)]), Qt.FillRule.WindingFill)
        if self._pointer is not None:
            painter.setBrush(QColor("#912D47"))
            painter.drawEllipse(self._pointer, 180, 180)
        painter.restore()


def view_controls(view: PaperView, expand: bool = True) -> QWidget:
    host = QWidget()
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    page = tool_button("fit-page", "Fit entire page", lambda: view.reset_view("page"))
    width = tool_button("fit-width", "Fit page width", lambda: view.reset_view("width"))
    page.setCheckable(True)
    width.setCheckable(True)
    layout.addWidget(page)
    layout.addWidget(width)
    if expand:
        layout.addStretch()
    else:
        layout.addWidget(tool_divider())
    layout.addWidget(tool_button("minus", "Zoom out", lambda: view.change_zoom(1 / 1.2)))
    value = label("Fit page", "muted")
    value.setAlignment(Qt.AlignmentFlag.AlignCenter)
    value.setMinimumWidth(62)
    def update(text: str) -> None:
        value.setText(text)
        page.setChecked(text == "Fit page")
        width.setChecked(text == "Fit width")
    view.zoom_changed.connect(update)
    update("Fit page" if view.fit == "page" else "Fit width")
    layout.addWidget(value)
    layout.addWidget(tool_button("plus", "Zoom in", lambda: view.change_zoom(1.2)))
    return host


class SettingsDialog(QDialog):
    def __init__(self, service: HuionApplication, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(560)
        self.service = service
        form = QFormLayout(self)
        form.setContentsMargins(24, 24, 24, 24)
        form.setVerticalSpacing(14)
        form.addRow(label("Settings", "title"))
        form.addRow(label(f"HuionNote {__version__}", "muted"))
        self.output = QLineEdit(service.output_directory)
        self.mac = QLineEdit(service.mac_address)
        self.mac.setPlaceholderText("Leave blank to find your notebook automatically")
        self.pin = QLineEdit(load_config().get("pin", ""))
        self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini = QLineEdit(service.gemini_key)
        self.gemini.setEchoMode(QLineEdit.EchoMode.Password)
        self.obsidian = QLineEdit(service.obsidian_vault)
        self.obsidian.setPlaceholderText("Optional Obsidian vault folder")
        form.addRow("Notes folder", self.output)
        form.addRow("", button("Choose folder…", self.choose_folder))
        form.addRow("Bluetooth address", self.mac)
        self.pin.setPlaceholderText("6 digits, if your notebook uses a PIN")
        form.addRow("Notebook PIN (optional)", self.pin)
        form.addRow("Gemini API key", self.gemini)
        form.addRow("Obsidian vault", self.obsidian)
        form.addRow("", button("Choose vault…", self.choose_vault))
        hint = label("Gemini receives only the pages you explicitly choose to transcribe.", "muted")
        hint.setWordWrap(True)
        form.addRow(hint)
        form.addRow(button("Erase notebook memory…", parent.clear_device, role="danger"))
        self.error = label("", "muted")
        self.error.setWordWrap(True)
        form.addRow(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save settings")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Notes folder", self.output.text())
        if path:
            self.output.setText(path)

    def choose_vault(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Obsidian vault", self.obsidian.text() or str(Path.home()))
        if path:
            self.obsidian.setText(path)

    def save(self) -> None:
        try:
            self.service.save_settings(self.output.text().strip(), self.gemini.text().strip(),
                                       self.mac.text().strip(), self.pin.text().strip(), self.obsidian.text().strip())
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
        app = QApplication.instance()
        app.setStyle("Fusion")
        palette = app.palette()
        for role, color in ((QPalette.ColorRole.Window, PAPER), (QPalette.ColorRole.Base, PAPER),
                            (QPalette.ColorRole.Text, INK), (QPalette.ColorRole.WindowText, INK),
                            (QPalette.ColorRole.Button, PAPER), (QPalette.ColorRole.ButtonText, INK),
                            (QPalette.ColorRole.PlaceholderText, MUTED),
                            (QPalette.ColorRole.Highlight, "#DCEAF2"), (QPalette.ColorRole.HighlightedText, INK)):
            palette.setColor(role, QColor(color))
        app.setPalette(palette)
        self.service = service or HuionApplication(pipeline, bridge)
        self._busy = False
        self._draft_dirty = False
        self._presentation = False
        self._live_history = []
        self._live_color_history = []
        self._live_background_history = []
        self._live_paths = []
        self._history_index = 0
        self._current_live = []
        self._current_colors = []
        self._current_background = None
        self._selected_note = None
        self._editor_dirty = False
        self._device_mode = None
        self._last_connected = False
        self._last_connection_error = ""
        self.setWindowTitle("HuionNote")
        self.resize(1280, 820)
        self.setMinimumSize(860, 580)
        self.setStyleSheet(STYLE)
        icon = ASSETS / "huionnote.png"
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
            strokes = self.service.live_draft()
            self.canvas.set_samples(strokes, self.service.live_colors)
            self.canvas.set_background(self.service.live_background)
            self.canvas.set_ink_color(self.service.ink_color)
            self._draft_dirty = False
            self.update_ink_menu()
        except Exception as exc:
            self.log(str(exc))
        self.update_live_controls()
        self.refresh_connection()
        self.load_library()
        self._show_page(0)
        for shortcut, callback in (
            ("F11", self.toggle_presentation), ("Escape", self.leave_presentation),
            ("Ctrl+F", self.focus_search), ("Ctrl+S", self.save_current),
            ("Ctrl+E", self.export_selected), ("Ctrl+N", self.new_page),
            ("Ctrl+Z", self.canvas_undo), ("Ctrl+Shift+Z", self.canvas_redo),
            ("Ctrl+Shift+E", lambda: self.set_live_tool("eraser")),
            ("Ctrl+Shift+H", lambda: self.set_live_tool("highlighter")),
            ("Ctrl+Shift+P", lambda: self.set_live_tool("pointer")),
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
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(str(ASSETS / "huionnote.png")).pixmap(36, 36))
        brand.addWidget(logo)
        brand.addWidget(label("HuionNote", "brand"))
        brand.addStretch()
        side.addLayout(brand)
        side.addSpacing(28)
        self.nav = []
        for i, title in enumerate(("Notes", "Live notebook", "Device")):
            item = button(title, lambda checked=False, n=i: self._show_page(n), role="nav")
            item.setCheckable(True)
            side.addWidget(item)
            self.nav.append(item)
        side.addStretch()
        self.activity_button = tool_button("activity", "Show activity log", self.toggle_activity, "Activity")
        self.activity_button.setObjectName("utility")
        self.activity_button.setCheckable(True)
        side.addWidget(self.activity_button, alignment=Qt.AlignmentFlag.AlignLeft)
        settings_button = tool_button("settings", "Open settings", self.open_settings, "Settings")
        settings_button.setObjectName("utility")
        side.addWidget(settings_button, alignment=Qt.AlignmentFlag.AlignLeft)
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
        self.pages.addWidget(self.device_page())
        column.addWidget(self.pages, 1)
        self.activity = QTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumHeight(110)
        self.activity.hide()
        column.addWidget(self.activity)
        root.addWidget(content, 1)
        self.setCentralWidget(shell)
        self.statusbar = QStatusBar()
        self.statusbar.setSizeGripEnabled(False)
        self.statusbar.setMinimumHeight(56)
        self.setStatusBar(self.statusbar)
        connection = QWidget()
        connection.setFixedWidth(180)
        status_layout = QHBoxLayout(connection)
        status_layout.setContentsMargins(0, 0, 12, 0)
        status_layout.setSpacing(10)
        bluetooth = QLabel()
        bluetooth.setPixmap(ui_icon("bluetooth").pixmap(18, 18))
        status_layout.addWidget(bluetooth)
        self.device_label = label("Connecting…", "muted")
        status_layout.addWidget(self.device_label, 1)
        status_layout.addWidget(tool_button("reconnect", "Reconnect to notebook", self.retry_connection))
        self.statusbar.addWidget(connection)
        self.footer = label("Originals stay on your notebook.", "muted")
        self.footer.setContentsMargins(12, 0, 12, 0)
        self.footer.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.statusbar.addWidget(self.footer, 1)
        self.storage_label = label("Storage · sync to estimate", "muted")
        self.storage_label.setContentsMargins(12, 0, 12, 0)
        self.statusbar.addPermanentWidget(self.storage_label)
        self.live_hint = label("Blank page", "muted")
        self.live_hint.setContentsMargins(12, 0, 16, 0)
        self.live_hint.setMinimumWidth(100)
        self.live_hint.setToolTip("The current draft is saved locally every 3 seconds. Save page adds it to Notes.")
        self.statusbar.addPermanentWidget(self.live_hint)
        self.live_view_controls = view_controls(self.canvas, expand=False)
        self.live_view_controls.layout().setSpacing(6)
        self.statusbar.addPermanentWidget(self.live_view_controls)
        self.statusbar.layout().setContentsMargins(16, 10, 16, 10)

    def library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 18, 24, 16)
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search pages, tags and transcripts")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search notes")
        self.search.textChanged.connect(self.refresh_notes)
        controls.addWidget(self.search, 1)
        self.filter = combo_box(["All pages", "Not transcribed", "Transcribed", "Transcription failed", "Favourites", "Needs review"],
                                "Filter pages by transcript status")
        self.filter.currentIndexChanged.connect(self.refresh_notes)
        controls.addWidget(self.filter)
        reload_button = button("Reload", self.load_library, role="quiet")
        reload_button.setToolTip("Reload pages from your notes folder")
        controls.addWidget(reload_button)
        layout.addLayout(controls)
        self.splitter = QSplitter()
        left = QWidget()
        list_layout = QVBoxLayout(left)
        list_layout.setContentsMargins(0, 8, 12, 0)
        list_header = QHBoxLayout()
        list_header.setContentsMargins(0, 0, 0, 0)
        self.library_count = label("0 pages", "muted")
        self.select_all_button = button("Select all", self.toggle_select_all, role="quiet")
        self.select_all_button.setToolTip("Select every page currently shown")
        list_header.addWidget(self.library_count)
        list_header.addStretch()
        list_header.addWidget(self.select_all_button)
        list_layout.addLayout(list_header)
        self.note_list = QListWidget()
        self.note_list.setItemDelegate(NoteDelegate(self.note_list))
        self.note_list.setMouseTracking(True)
        self.note_list.setAccessibleName("Saved pages")
        self.note_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.note_list.setWordWrap(True)
        self.note_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.note_list.itemSelectionChanged.connect(self.selection_changed)
        self.note_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.note_list.customContextMenuRequested.connect(self.note_menu)
        list_layout.addWidget(self.note_list, 1)
        self.empty_list = label("No saved pages. Sync your notebook to import them.", "muted")
        self.empty_list.setWordWrap(True)
        list_layout.addWidget(self.empty_list)
        actions = QHBoxLayout()
        self.export_button = button("Export…", self.export_selected)
        self.transcribe_button = button("Transcribe…", self.transcribe_selected)
        self.delete_button = tool_button("delete", "Delete selected pages…", self.delete_selected)
        self.organize_button = tool_button("organize", "Organise selected page", self.organize_selected)
        actions.addWidget(self.export_button)
        actions.addWidget(self.transcribe_button)
        actions.addWidget(self.organize_button)
        actions.addWidget(self.delete_button)
        list_layout.addLayout(actions)
        self.obsidian_button = button("Send to Obsidian Inbox", self.send_to_obsidian)
        self.obsidian_button.setToolTip("Publish selected pages as Markdown and mobile-friendly PNGs")
        self.obsidian_button.setEnabled(False)
        list_layout.addWidget(self.obsidian_button)
        self.splitter.addWidget(left)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(16, 8, 0, 0)
        self.note_title = label("Preview", "title")
        self.note_title.setWordWrap(True)
        detail_layout.addWidget(self.note_title)
        self.note_meta = label("", "muted")
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
        self.editor.setPlaceholderText("Write or edit the transcript. Use Transcribe to convert the handwriting first.")
        self.editor.setAccessibleName("Edit page transcript")
        self.editor.textChanged.connect(self.editor_changed)
        self.review_splitter.addWidget(self.review_preview)
        self.review_splitter.addWidget(self.editor)
        self.review_splitter.setChildrenCollapsible(False)
        self.review_splitter.setSizes([400, 400])
        review_layout.addWidget(self.review_splitter, 1)
        self.save_transcript_button = button("Save changes", self.save_transcript)
        self.save_transcript_button.setEnabled(False)
        review_actions = QHBoxLayout()
        self.review_button = button("Mark reviewed", self.mark_reviewed)
        self.review_button.setEnabled(False)
        review_actions.addStretch()
        review_actions.addWidget(self.review_button)
        review_actions.addWidget(self.save_transcript_button)
        review_layout.addLayout(review_actions)
        self.detail_tabs.addTab(review, "Edit transcript")
        self.detail_tabs.currentChanged.connect(self.active_preview_changed)
        detail_layout.addWidget(self.detail_tabs, 1)
        self.no_selection = label("Select a page to preview your handwriting.", "empty")
        self.no_selection.setWordWrap(True)
        self.no_selection.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_layout.addWidget(self.no_selection, 1)
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
        tools.setSpacing(4)
        self.live_position = label("Current page", "muted")
        self.previous_page_button = tool_button("previous", "Previous saved page", lambda: self.browse_live(-1))
        self.next_page_button = tool_button("next", "Next page", lambda: self.browse_live(1))
        tools.addWidget(self.previous_page_button)
        tools.addWidget(self.live_position)
        tools.addWidget(self.next_page_button)
        tools.addWidget(tool_divider())
        self.paper_choice = combo_box(["Plain", "Ruled", "Grid", "Dotted"], "Paper guides")
        self.paper_choice.setObjectName("paperChoice")
        self.paper_choice.setToolTip("Paper guides are for viewing only; exported pages stay plain.")
        self.paper_choice.currentTextChanged.connect(self.change_paper)
        tools.addWidget(self.paper_choice)
        self.ink_button = tool_button("color", "Ink colour", lambda: None)
        self.ink_button.setObjectName("inkChoice")
        self.ink_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.ink_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.ink_menu = QMenu(self)
        self.ink_actions = {}
        for name, color in (("Graphite", INK), ("Blue", "#2457A7"), ("Burgundy", "#912D47"), ("Green", "#28704B")):
            swatch = QPixmap(16, 16)
            swatch.fill(QColor(color))
            action = self.ink_menu.addAction(QIcon(swatch), name)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, color=color: self.change_ink(color))
            self.ink_actions[color] = action
        self.ink_menu.addSeparator()
        self.ink_menu.addAction("Custom colour…", self.choose_ink)
        self.ink_button.setMenu(self.ink_menu)
        tools.addWidget(self.ink_button)
        self.image_button = tool_button("image", "Page image", lambda: None, "Image")
        self.image_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.image_menu = QMenu(self)
        self.image_menu.addAction(ui_icon("image"), "Choose image…", self.choose_live_image)
        self.image_menu.addAction(ui_icon("rotate"), "Rotate 90°", lambda: self.adjust_live_image(rotate=90))
        self.image_menu.addAction(ui_icon("crop"), "Crop and position…", self.crop_live_image)
        self.image_menu.addAction(ui_icon("opacity"), "Adjust opacity…", self.adjust_live_opacity)
        self.remove_image_action = self.image_menu.addAction(ui_icon("delete"), "Remove image", self.remove_live_image)
        self.remove_image_action.setEnabled(False)
        self.image_button.setMenu(self.image_menu)
        tools.addWidget(self.image_button)
        tools.addWidget(tool_divider())
        self.undo_button = tool_button("undo", "Undo last stroke", self.canvas_undo)
        self.redo_button = tool_button("redo", "Redo stroke", self.canvas_redo)
        tools.addWidget(self.undo_button)
        tools.addWidget(self.redo_button)
        self.eraser_button = tool_button("eraser", "Erase strokes", lambda: self.set_live_tool("eraser"))
        self.eraser_button.setCheckable(True)
        self.highlighter_button = tool_button("highlighter", "Highlighter", lambda: self.set_live_tool("highlighter"))
        self.highlighter_button.setCheckable(True)
        self.pointer_button = tool_button("pointer", "Presentation pointer", lambda: self.set_live_tool("pointer"))
        self.pointer_button.setCheckable(True)
        tools.addWidget(self.eraser_button)
        tools.addWidget(self.highlighter_button)
        tools.addWidget(self.pointer_button)
        tools.addStretch()
        tools.addWidget(tool_button("save", "Save page to Notes (Ctrl+S)", self.save_live))
        tools.addWidget(tool_button("new", "Save and start a new page (Ctrl+N)", self.new_page))
        tools.addWidget(tool_divider())
        self.present_button = tool_button("present", "Present page (F11). Press Escape to return.", self.toggle_presentation, "Present")
        tools.addWidget(self.present_button)
        layout.addWidget(self.live_toolbar)
        self.canvas = LiveCanvas()
        layout.addWidget(self.canvas, 1)
        self.canvas.setToolTip("Ctrl+scroll to zoom. Drag to pan.")
        return page

    def device_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        intro = label("Manage what stays on your notebook and what is safely copied to this computer.", "muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        status = QGroupBox("Notebook status")
        status_layout = QHBoxLayout(status)
        self.device_state_large = label("Connecting…", "title")
        self.device_storage_large = label("Storage unknown", "metric")
        self.device_last_sync = label("Sync to estimate remaining pages.", "muted")
        storage_column = QVBoxLayout()
        storage_column.addWidget(self.device_storage_large)
        storage_column.addWidget(self.device_last_sync)
        status_layout.addWidget(self.device_state_large)
        status_layout.addStretch()
        status_layout.addLayout(storage_column)
        layout.addWidget(status)

        transfer = QGroupBox("Transfer pages")
        transfer_layout = QVBoxLayout(transfer)
        safe_row = QHBoxLayout()
        safe_copy = QVBoxLayout()
        safe_copy.addWidget(label("Sync notebook", "brand"))
        safe_text = label("Copy new pages to Notes and keep the originals on the X10.", "muted")
        safe_text.setWordWrap(True)
        safe_copy.addWidget(safe_text)
        safe_row.addLayout(safe_copy, 1)
        self.device_sync_button = button("Sync notebook", self.sync_now, True)
        safe_row.addWidget(self.device_sync_button)
        transfer_layout.addLayout(safe_row)
        transfer_layout.addSpacing(12)
        free_row = QHBoxLayout()
        free_copy = QVBoxLayout()
        free_copy.addWidget(label("Sync & free space", "brand"))
        free_text = label("Save each page locally, verify it, then remove that transferred page from the X10.", "muted")
        free_text.setWordWrap(True)
        free_copy.addWidget(free_text)
        free_row.addLayout(free_copy, 1)
        self.sync_clear_button = button("Sync and free space…", self.confirm_sync_and_clear)
        free_row.addWidget(self.sync_clear_button)
        transfer_layout.addLayout(free_row)
        self.auto_sync_check = QCheckBox("Automatically sync when the notebook connects")
        self.auto_sync_check.setChecked(self.service.auto_sync)
        self.auto_sync_check.setToolTip("Automatic sync only copies pages. It never removes pages from the notebook.")
        self.auto_sync_check.toggled.connect(self.service.set_auto_sync)
        transfer_layout.addWidget(self.auto_sync_check)
        layout.addWidget(transfer)

        history = QGroupBox("Recent activity")
        history_layout = QVBoxLayout(history)
        self.sync_history = QTextBrowser()
        self.sync_history.setMaximumHeight(130)
        self.sync_history.setPlainText("No sync activity in this session.")
        history_layout.addWidget(self.sync_history)
        layout.addWidget(history)

        danger = QGroupBox("Erase notebook memory")
        danger_layout = QHBoxLayout(danger)
        danger_copy = label("Permanently remove every stored page. Pages already saved on this computer are kept.", "muted")
        danger_copy.setWordWrap(True)
        danger_layout.addWidget(danger_copy, 1)
        self.erase_device_button = button("Erase notebook memory…", self.clear_device, role="danger")
        danger_layout.addWidget(self.erase_device_button)
        layout.addWidget(danger)
        layout.addStretch()
        return page

    def update_ink_menu(self) -> None:
        color = self.canvas.ink_color
        name = color
        for value, action in self.ink_actions.items():
            action.setChecked(value == color)
            if value == color:
                name = action.text()
        self.ink_button.setToolTip(f"Ink colour · {name}. Applies to new strokes; existing ink is kept.")
        self.ink_button.setAccessibleName(f"Ink colour: {name}")
        self.ink_button.setText(name)

    def change_ink(self, color: str) -> None:
        self.canvas.set_ink_color(color)
        self.update_ink_menu()

    def choose_ink(self) -> None:
        color = QColorDialog.getColor(QColor(self.canvas.ink_color), self, "Ink colour",
                                      QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if color.isValid():
            self.change_ink(color.name())

    def choose_live_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose an image to annotate", str(Path.home()),
            "Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)")
        if not path:
            return
        if self._history_index < len(self._live_history):
            self.browse_live(len(self._live_history) - self._history_index)
        try:
            self.canvas.set_background(self.service.import_live_background(path))
            self.live_changed()
            self.save_draft()
            self.log("Page image ready for annotation.")
        except Exception as exc:
            QMessageBox.warning(self, "Image could not be added", str(exc))

    def adjust_live_image(self, *, rotate: int = 0, crop: bool = False, opacity: int = 100,
                          position: str = "centre") -> None:
        try:
            path = self.service.adjust_live_background(rotate=rotate, crop_to_page=crop, opacity=opacity, position=position)
            self.canvas.set_background(path)
            self.live_changed()
            self.save_draft()
            self.log("Page image updated. The original file is unchanged.")
        except Exception as exc:
            QMessageBox.warning(self, "Image could not be adjusted", str(exc))

    def adjust_live_opacity(self) -> None:
        value, accepted = QInputDialog.getInt(self, "Image opacity", "Opacity", 70, 10, 100, 5)
        if accepted:
            self.adjust_live_image(opacity=value)

    def crop_live_image(self) -> None:
        choice, accepted = QInputDialog.getItem(
            self, "Crop and position", "Keep this part of the image", ["Centre", "Left", "Right", "Top", "Bottom"], 0, False)
        if accepted:
            self.adjust_live_image(crop=True, position=choice.casefold())

    def remove_live_image(self) -> None:
        if self._history_index < len(self._live_history):
            self.browse_live(len(self._live_history) - self._history_index)
        self.service.clear_live_background()
        self.canvas.set_background(None)
        self.live_changed()
        self.save_draft()
        self.log("Page image removed. The original file was not changed.")

    def change_paper(self, style: str) -> None:
        self.canvas.paper_style = style
        self.canvas.update()

    def set_live_tool(self, tool: str) -> None:
        if self.canvas.tool == tool:
            tool = "ink"
        self.canvas.set_tool(tool)
        self.eraser_button.setChecked(tool == "eraser")
        self.highlighter_button.setChecked(tool == "highlighter")
        self.pointer_button.setChecked(tool == "pointer")
        self.live_hint.setText({"ink": "Ink", "eraser": "Eraser", "highlighter": "Highlighter",
                                "pointer": "Pointer"}[tool])

    def canvas_undo(self) -> None:
        if self._history_index == len(self._live_history):
            self.canvas.undo()

    def canvas_redo(self) -> None:
        if self._history_index == len(self._live_history):
            self.canvas.redo()

    def _show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.page_title.setText(("Notes", "Live notebook", "Device")[index])
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)
        self.live_hint.setVisible(index == 1)
        self.live_view_controls.setVisible(index == 1)
        self.sync_button.setVisible(index != 2)
        mode = "tablet" if index == 1 else "notes"
        if mode != self._device_mode:
            self._device_mode = mode
            self.service.start_notes() if mode == "notes" else self.service.start_stream()
        if not self._busy:
            self.footer.setText("" if index == 1 else "Originals stay on your notebook.")

    def toggle_activity(self) -> None:
        self.activity.setVisible(self.activity_button.isChecked())

    def focus_search(self) -> None:
        self.leave_presentation()
        self._show_page(0)
        self.search.setFocus()

    def refresh_connection(self) -> None:
        snapshot = self.service.device_snapshot()
        error = snapshot.error.strip()
        if snapshot.connected is True:
            state = "live" if self.pages.currentIndex() == 1 else "paired"
            self.device_label.setText(f"X10 {state}" + (f" · {snapshot.battery}%" if snapshot.battery is not None else ""))
            self.device_label.setToolTip(
                ("Live pen streaming" if state == "live" else "Notebook paired; live streaming is off")
                + (f" · {snapshot.battery}% battery" if snapshot.battery is not None else ""))
        elif snapshot.connected is None:
            self.device_label.setText("Retrying…" if error else "Connecting…")
            self.device_label.setToolTip(error or "Connecting to X10. Touch the paper with your pen to wake it.")
        else:
            self.device_label.setText("X10 offline")
            self.device_label.setToolTip(error or "Notebook disconnected. Saved pages remain available; use Reconnect to try again.")
        if error and error != self._last_connection_error:
            self.log(f"Notebook connection: {error}")
        self._last_connection_error = error
        if snapshot.stored_pages is None:
            self.storage_label.setText("Storage · sync to estimate")
            self.storage_label.setToolTip("Sync the X10 to estimate free pages. Local page counts do not measure notebook storage.")
        else:
            free = max(0, 50 - snapshot.stored_pages)
            self.storage_label.setText(f"Storage · ~{free}/50 free")
            self.storage_label.setToolTip(
                f"Estimated from {snapshot.stored_pages} stored pages at the last complete sync ({snapshot.storage_checked_at}). "
                "Huion specifies up to 50 pages, not a byte-level capacity. New writing or changes in another app can change this. "
                "Syncing or deleting local files does not free notebook memory.")
        if hasattr(self, "device_state_large"):
            self.device_state_large.setText(self.device_label.text())
            if snapshot.stored_pages is None:
                self.device_storage_large.setText("Storage unknown")
                self.device_last_sync.setText("Sync to estimate remaining pages.")
            else:
                free = max(0, 50 - snapshot.stored_pages)
                self.device_storage_large.setText(f"~{free} of 50 pages free")
                self.device_last_sync.setText(f"Estimated from the last complete sync · {snapshot.storage_checked_at}")
        connected = snapshot.connected is True
        if connected and not self._last_connected and self.service.auto_sync and not self._busy and self.pages.currentIndex() != 1:
            QTimer.singleShot(250, self.sync_now)
        self._last_connected = connected

    def retry_connection(self) -> None:
        if not self._busy:
            live = self.pages.currentIndex() == 1
            threading.Thread(target=lambda: self.service.retry_connection(live), daemon=True).start()
            self.log("Reconnecting to notebook…")

    def load_library(self) -> None:
        try:
            self._all_notes = self.service.load_notes()
            self._search_text = {}
            self._metadata = {}
            for note in self._all_notes:
                metadata = self.service.note_metadata(note)
                self._metadata[note.svg_path] = metadata
                text = " ".join((metadata.get("title", ""), metadata.get("collection", ""),
                                 " ".join(metadata.get("tags", [])), Path(note.svg_path).stem.replace("_", " ")))
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
            metadata = self._metadata.get(note.svg_path, {})
            if filter_index == 1 and note.status not in (NoteStatus.SYNCED, NoteStatus.CONVERTING):
                continue
            if filter_index == 2 and note.status != NoteStatus.CONVERTED:
                continue
            if filter_index == 3 and note.status != NoteStatus.FAILED:
                continue
            if filter_index == 4 and not metadata.get("favourite"):
                continue
            if filter_index == 5 and (note.status != NoteStatus.CONVERTED or metadata.get("reviewed")):
                continue
            title = metadata.get("title") or Path(note.svg_path).stem.replace("_", " ").title()
            status = {NoteStatus.SYNCED: "Not transcribed", NoteStatus.CONVERTING: "Transcribing…",
                      NoteStatus.CONVERTED: "Transcribed", NoteStatus.FAILED: "Transcription failed"}[note.status]
            if note.status == NoteStatus.CONVERTED and not metadata.get("reviewed"):
                status = "Needs review"
            if metadata.get("favourite"):
                title = f"★ {title}"
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
        self.empty_list.setText("No matches. Clear the search or change the filter." if self._all_notes else "No saved pages. Sync your notebook to import them.")
        self.selection_changed()

    def selected_notes(self) -> list:
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.note_list.selectedItems()]

    def toggle_select_all(self) -> None:
        if self.note_list.count() and len(self.note_list.selectedItems()) < self.note_list.count():
            self.note_list.selectAll()
        else:
            self.note_list.clearSelection()

    def selection_changed(self) -> None:
        notes = self.selected_notes()
        self.export_button.setEnabled(bool(notes) and not self._busy)
        self.transcribe_button.setEnabled(bool(notes) and not self._busy)
        self.delete_button.setEnabled(bool(notes) and not self._busy)
        self.obsidian_button.setEnabled(bool(notes) and not self._busy)
        self.organize_button.setEnabled(len(notes) == 1 and not self._busy)
        all_selected = bool(self.note_list.count()) and len(notes) == self.note_list.count()
        self.select_all_button.setText("Clear selection" if all_selected else "Select all")
        self.select_all_button.setEnabled(bool(self.note_list.count()) and not self._busy)
        self.library_count.setText(f"{self.note_list.count()} pages · {len(notes)} selected" if notes else
                                   f"{self.note_list.count()} page{'s' if self.note_list.count() != 1 else ''}")
        if not notes:
            if self._editor_dirty:
                return
            self._selected_note = None
            self.note_title.setText("Preview")
            self.note_meta.hide()
            self.preview_controls.hide()
            self.detail_tabs.hide()
            self.no_selection.show()
            self.editor.setEnabled(False)
            self.save_transcript_button.setEnabled(False)
            self.review_button.setEnabled(False)
            return
        self.no_selection.hide()
        self.note_meta.show()
        self.detail_tabs.show()
        self.active_preview_changed(self.detail_tabs.currentIndex())
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
        metadata = self._metadata.get(note.svg_path, {})
        self.note_title.setText(metadata.get("title") or Path(note.svg_path).stem.replace("_", " ").title())
        self.note_meta.setText(f"{note.synced_at:%d %B %Y, %H:%M} · {len(notes)} selected" if len(notes) > 1 else f"{note.synced_at:%d %B %Y, %H:%M}")
        self.preview.set_svg(note.svg_path)
        self.review_preview.set_svg(note.svg_path)
        markdown = Path(note.markdown_path).read_text(encoding="utf-8") if note.markdown_path and Path(note.markdown_path).exists() else ""
        self.reader.document().setBaseUrl(QUrl.fromLocalFile(str(Path(note.svg_path).parent) + "/"))
        self.reader.setMarkdown(markdown or "## No transcript yet\n\nChoose **Transcribe** to convert this page to text, or open **Edit transcript** to write your own.")
        self.editor.setPlainText(markdown)
        self._editor_dirty = False
        self.save_transcript_button.setEnabled(False)
        self.review_button.setEnabled(note.status == NoteStatus.CONVERTED and not metadata.get("reviewed") and not self._busy)

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

    def adapt_live_toolbar(self) -> None:
        compact = self.width() < 1050
        style = (Qt.ToolButtonStyle.ToolButtonIconOnly if compact
                 else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for control in (self.ink_button, self.image_button, self.present_button):
            control.setToolButtonStyle(style)
        self.live_position.setVisible(not compact)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if hasattr(self, "review_splitter"):
            QTimer.singleShot(0, self.adapt_review)
        if hasattr(self, "live_toolbar"):
            QTimer.singleShot(0, self.adapt_live_toolbar)

    def editor_changed(self) -> None:
        self._editor_dirty = True
        self.save_transcript_button.setEnabled(self._selected_note is not None and not self._busy)

    def save_transcript(self) -> bool:
        if not self._selected_note:
            return True
        try:
            self.service.save_markdown(self._selected_note, self.editor.toPlainText())
            self._editor_dirty = False
            self.save_transcript_button.setEnabled(False)
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
        menu.addAction("Send to Obsidian Inbox", self.send_to_obsidian)
        if len(self.selected_notes()) == 1:
            menu.addAction(ui_icon("organize"), "Rename and organise…", self.organize_selected)
        menu.addAction("Open handwriting externally", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.selected_notes()[0].svg_path)))
        menu.addSeparator()
        menu.addAction(ui_icon("delete"), "Delete selected pages…", self.delete_selected)
        menu.exec(self.note_list.mapToGlobal(position))

    def organize_selected(self) -> None:
        notes = self.selected_notes()
        if len(notes) != 1 or self._busy:
            return
        note = notes[0]
        metadata = self.service.note_metadata(note)
        dialog = QDialog(self)
        dialog.setWindowTitle("Organise page")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(label("Page details", "title"))
        form = QFormLayout()
        title = QLineEdit(metadata.get("title") or Path(note.svg_path).stem.replace("_", " ").title())
        tags = QLineEdit(", ".join(metadata.get("tags", [])))
        tags.setPlaceholderText("meeting, project, follow-up")
        collection = QLineEdit(metadata.get("collection", ""))
        collection.setPlaceholderText("Optional notebook or project")
        favourite = QCheckBox("Favourite")
        favourite.setChecked(bool(metadata.get("favourite")))
        form.addRow("Title", title)
        form.addRow("Tags", tags)
        form.addRow("Collection", collection)
        form.addRow("", favourite)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save details")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.service.update_note_metadata(note, title=title.text(),
                                              tags=[value.strip() for value in tags.text().split(",")],
                                              collection=collection.text(), favourite=favourite.isChecked())
            self.load_library()
            self.log("Page details saved.")

    def mark_reviewed(self) -> None:
        if not self._selected_note:
            return
        metadata = self.service.note_metadata(self._selected_note)
        self.service.update_note_metadata(
            self._selected_note,
            title=metadata.get("title", ""), tags=metadata.get("tags", []),
            collection=metadata.get("collection", ""), favourite=metadata.get("favourite", False), reviewed=True)
        self.load_library()
        self.log("Transcript marked as reviewed.")

    def delete_selected(self) -> None:
        notes = self.selected_notes()
        if not notes or self._busy or not self.resolve_editor():
            return
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle("Delete saved pages?")
        confirmation.setText(f"Move {len(notes)} selected page{'s' if len(notes) != 1 else ''} to Trash?")
        confirmation.setInformativeText("Handwriting, pen data, transcripts and local preview images will be moved together. "
                                        "Restore them from your desktop Trash if needed. Notebook originals and the live draft are kept.")
        confirmation.addButton(QMessageBox.StandardButton.Cancel)
        delete = QPushButton("Move to Trash")
        delete.setObjectName("danger")
        confirmation.addButton(delete, QMessageBox.ButtonRole.DestructiveRole)
        confirmation.setDefaultButton(QMessageBox.StandardButton.Cancel)
        confirmation.exec()
        if confirmation.clickedButton() == delete:
            if not self.save_draft():
                return
            self.run_job("Delete", lambda: self.service.delete_notes(notes))

    def refresh_live_history(self) -> None:
        kept = [i for i, path in enumerate(self._live_paths) if Path(path).exists()]
        old_index = self._history_index
        was_browsing = old_index < len(self._live_history)
        self._live_history = [self._live_history[i] for i in kept]
        self._live_color_history = [self._live_color_history[i] for i in kept]
        self._live_background_history = [self._live_background_history[i] for i in kept]
        self._live_paths = [self._live_paths[i] for i in kept]
        self._history_index = kept.index(old_index) if old_index in kept else len(kept)
        if was_browsing and old_index not in kept:
            self.canvas.set_samples(self._current_live, self._current_colors)
            self.canvas.set_background(self._current_background)
        self.live_position.setText("Current page" if self._history_index == len(kept) else f"Saved page {self._history_index + 1}")
        self.update_live_controls()

    def run_job(self, name: str, work: Any) -> None:
        if self._busy:
            return
        self._busy = True
        self.sync_button.setEnabled(False)
        self.select_all_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.transcribe_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.obsidian_button.setEnabled(False)
        self.organize_button.setEnabled(False)
        self.save_transcript_button.setEnabled(False)
        self.review_button.setEnabled(False)
        for control in (getattr(self, "device_sync_button", None), getattr(self, "sync_clear_button", None),
                        getattr(self, "erase_device_button", None)):
            if control:
                control.setEnabled(False)
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
        self.select_all_button.setEnabled(bool(self.note_list.count()))
        self.export_button.setEnabled(bool(self.selected_notes()))
        self.transcribe_button.setEnabled(bool(self.selected_notes()))
        self.delete_button.setEnabled(bool(self.selected_notes()))
        self.obsidian_button.setEnabled(bool(self.selected_notes()))
        self.organize_button.setEnabled(len(self.selected_notes()) == 1)
        self.save_transcript_button.setEnabled(self._editor_dirty and self._selected_note is not None)
        for control in (getattr(self, "device_sync_button", None), getattr(self, "sync_clear_button", None),
                        getattr(self, "erase_device_button", None)):
            if control:
                control.setEnabled(True)

    def job_complete(self, name: str, result: Any) -> None:
        self.finish_job()
        if name == "Delete":
            self.refresh_live_history()
        self.refresh_connection()
        count = len(result) if isinstance(result, list) else 0
        self.log(f"{name} complete · {count} file{'s' if count != 1 else ''}" if name == "Export" else f"{name} complete.")
        self.load_library()
        if name == "Delete":
            self.log("Selected page files moved to Trash. Notebook originals are unchanged.")
        if name == "Transcription" and self._selected_note and not self._editor_dirty:
            self._selected_note = None
            self.selection_changed()
        if name == "Sync":
            self._show_page(0)
            self.log(f"Synced {count} pages. Originals remain on the notebook.")
        elif name == "Sync & free space":
            self.log(f"Saved and removed {count} notebook page{'s' if count != 1 else ''}.")
        elif name == "Obsidian":
            pages = count // 2
            self.log(f"Sent {pages} page{'s' if pages != 1 else ''} to Obsidian Inbox.")
        if name in {"Sync", "Sync & free space", "Clear notebook memory"} and hasattr(self, "sync_history"):
            stamp = __import__("datetime").datetime.now().strftime("%H:%M")
            summary = (f"{stamp} · {name} · {count} page{'s' if count != 1 else ''}"
                       if name != "Clear notebook memory" else f"{stamp} · Notebook memory erased")
            if self.sync_history.toPlainText().startswith("No sync activity"):
                self.sync_history.clear()
            self.sync_history.append(summary)

    def job_error(self, name: str, message: str) -> None:
        self.finish_job()
        if name == "Delete":
            self.refresh_live_history()
        self.load_library()
        if name == "Transcription" and self._selected_note and not self._editor_dirty:
            self._selected_note = None
            self.selection_changed()
        self.log(f"{name} failed: {message}")
        QMessageBox.warning(self, f"{name} could not finish", message)

    def sync_now(self) -> None:
        self.run_job("Sync", lambda: self.service.sync(progress=self.job_progress.emit))

    def confirm_sync_and_clear(self) -> None:
        if self._busy:
            return
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle("Sync and free notebook space?")
        confirmation.setText("Copy stored pages, then remove each successfully saved page from the X10?")
        confirmation.setInformativeText("A page is removed only after its local files are written. If transfer stops, pages not yet saved remain on the notebook.")
        confirmation.addButton(QMessageBox.StandardButton.Cancel)
        proceed = QPushButton("Sync and free space")
        proceed.setObjectName("primary")
        confirmation.addButton(proceed, QMessageBox.ButtonRole.AcceptRole)
        confirmation.setDefaultButton(QMessageBox.StandardButton.Cancel)
        confirmation.exec()
        if confirmation.clickedButton() == proceed:
            self.run_job("Sync & free space", lambda: self.service.sync_and_free_space(progress=self.job_progress.emit))

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
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        dialog.setMinimumWidth(440)
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
        combined = QCheckBox("One combined PDF · selected pages in library order")
        combined.setEnabled(len(notes) > 1)
        layout.addWidget(combined)
        export_hint = label("Existing files won't be overwritten. Transcripts and pen data are included only when available.", "muted")
        export_hint.setWordWrap(True)
        layout.addWidget(export_hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Choose folder…")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        formats = [fmt for fmt, check in checks.items() if check.isChecked()]
        if not formats and not combined.isChecked():
            return
        directory = QFileDialog.getExistingDirectory(self, "Export destination")
        if directory:
            def work() -> list:
                exported = self.service.export_notes(notes, directory, formats, self.job_progress.emit) if formats else []
                if combined.isChecked():
                    exported.append(self.service.export_combined_pdf(notes, str(Path(directory) / "HuionNote pages.pdf"), self.job_progress.emit))
                return exported
            self.run_job("Export", work)

    def transcribe_selected(self) -> None:
        notes = [n for n in self.selected_notes() if n.status in (NoteStatus.SYNCED, NoteStatus.FAILED)]
        if not notes or self._busy:
            if not self._busy:
                self.log("The selected pages already have transcripts. Use Edit transcript to make changes.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Transcribe handwriting")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        dialog.setMinimumWidth(440)
        layout.addWidget(label(f"Transcribe {len(notes)} page{'s' if len(notes) != 1 else ''}", "title"))
        cloud_hint = label("Sends only these selected pages to Google Gemini. Requires an API key in Settings.", "muted")
        cloud_hint.setWordWrap(True)
        layout.addWidget(cloud_hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Transcribe")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not self.service.gemini_key:
            QMessageBox.information(self, "Add a Gemini key", "Add your Gemini API key in Settings, then try again.")
            return
        def work() -> list:
            failures = []
            for index, note in enumerate(notes):
                try:
                    self.service.convert(note)
                except Exception as exc:
                    failures.append(f"{Path(note.svg_path).name}: {exc}")
                self.job_progress.emit(index + 1, len(notes))
            if failures:
                raise RuntimeError("Some pages could not be transcribed. Successful pages were saved.\n\n" + "\n".join(failures))
            return notes
        self.run_job("Transcription", work)

    def send_to_obsidian(self) -> None:
        notes = self.selected_notes()
        if not notes or self._busy:
            return
        if not self.service.obsidian_vault:
            QMessageBox.information(
                self, "Choose your Obsidian vault",
                "Set the vault folder once in Settings, then use Send to Obsidian Inbox again.")
            self.open_settings()
            return
        self.run_job("Obsidian", lambda: self.service.publish_to_obsidian(notes, self.job_progress.emit))

    def receive_point(self, point: Any) -> None:
        if self._history_index < len(self._live_history):
            self._history_index = len(self._live_history)
            self.canvas.set_samples(self._current_live, self._current_colors)
            self.canvas.set_background(self._current_background)
            self.live_position.setText("Current page")
            self.update_live_controls()
        self.canvas.add_point(point)

    def live_changed(self) -> None:
        self._draft_dirty = True
        self.update_live_controls()

    def update_live_controls(self) -> None:
        self.previous_page_button.setEnabled(self._history_index > 0)
        self.next_page_button.setEnabled(self._history_index < len(self._live_history))
        self.remove_image_action.setEnabled(self.canvas.has_background())
        editing = self._history_index == len(self._live_history)
        self.undo_button.setEnabled(editing and self.canvas.can_undo())
        self.redo_button.setEnabled(editing and self.canvas.can_redo())
        self.eraser_button.setEnabled(editing)
        self.highlighter_button.setEnabled(editing)
        if self._history_index < len(self._live_history):
            text = "Saved page"
        elif self._draft_dirty:
            text = "Unsaved changes"
        else:
            text = "Draft saved" if self.canvas.samples() or self.canvas.has_background() else "Blank page"
        self.live_hint.setText(text)

    def save_draft(self) -> bool:
        if self._history_index < len(self._live_history):
            return True
        if not self._draft_dirty:
            return True
        try:
            self.service.save_live_draft(self.canvas.samples(), self.canvas.colors(), self.canvas.ink_color)
            self._draft_dirty = False
            self.update_live_controls()
            return True
        except Exception as exc:
            self.live_hint.setText("Draft not saved")
            self.log(f"Live page could not be saved: {exc}. Export or check the notes folder.")
            return False

    def save_live(self) -> bool:
        if self._history_index < len(self._live_history):
            self._last_live_path = self._live_paths[self._history_index]
            return True
        if not self.canvas.samples() and not self.canvas.has_background():
            self.log("Write on the notebook or add an image before saving a page.")
            return False
        try:
            self._last_live_path = self.service.save_live_page(self.canvas.samples(), self.canvas.colors(), self.canvas.ink_color)
            self._draft_dirty = False
            self.update_live_controls()
            self.log("Live page saved to Notes.")
            self.load_library()
            return True
        except Exception as exc:
            QMessageBox.warning(self, "Page could not be saved", str(exc))
            return False

    def new_page(self) -> None:
        if self._history_index < len(self._live_history):
            self.browse_live(len(self._live_history) - self._history_index)
        if self.canvas.samples() or self.canvas.has_background():
            if not self.save_live():
                return
            self._live_history.append(self.canvas.samples())
            self._live_color_history.append(self.canvas.colors())
            self._live_background_history.append(self.canvas.background_image())
            self._live_paths.append(self._last_live_path)
        try:
            self.service.new_live_page()
        except Exception as exc:
            self.log(f"Could not start a new page: {exc}")
            return
        self.canvas.set_samples([])
        self.canvas.set_background(None)
        self._history_index = len(self._live_history)
        self._current_live = []
        self._current_colors = []
        self._current_background = None
        self._draft_dirty = False
        self.live_position.setText("Current page")
        self.update_live_controls()
        self.canvas.reset_view()

    def browse_live(self, direction: int) -> None:
        target = max(0, min(len(self._live_history), self._history_index + direction))
        if target == self._history_index:
            return
        if self._history_index == len(self._live_history):
            if not self.save_draft():
                return
            self._current_live = self.canvas.samples()
            self._current_colors = self.canvas.colors()
            self._current_background = self.canvas.background_image()
        self._history_index = target
        self.canvas.set_samples(self._current_live if target == len(self._live_history) else self._live_history[target],
                                self._current_colors if target == len(self._live_history) else self._live_color_history[target])
        self.canvas.set_background(self._current_background if target == len(self._live_history)
                                   else self._live_background_history[target])
        self.live_position.setText("Current page" if target == len(self._live_history) else f"Saved page {target + 1}")
        self.update_live_controls()
        self.canvas.reset_view()

    def toggle_presentation(self) -> None:
        if self._presentation:
            self.leave_presentation()
            return
        self._show_page(1)
        self._was_maximized = self.isMaximized()
        self._presentation = True
        for widget in (self.sidebar, self.topbar, self.live_toolbar, self.statusbar, self.activity, self.progress):
            widget.hide()
        self.showFullScreen()
        self.canvas.reset_view()

    def leave_presentation(self) -> None:
        if not self._presentation:
            return
        self._presentation = False
        for widget in (self.sidebar, self.topbar, self.live_toolbar, self.statusbar):
            widget.show()
        self.activity.setVisible(self.activity_button.isChecked())
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
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle("Erase notebook memory?")
        confirmation.setIcon(QMessageBox.Icon.Warning)
        confirmation.setText("Permanently erase all pages stored on the X10?")
        confirmation.setInformativeText("Pages saved on this computer are kept. Pages you haven't synced will be lost. Sync and check your saved pages before erasing.")
        confirmation.addButton(QMessageBox.StandardButton.Cancel)
        erase = QPushButton("Erase notebook memory")
        erase.setObjectName("danger")
        confirmation.addButton(erase, QMessageBox.ButtonRole.DestructiveRole)
        confirmation.setDefaultButton(QMessageBox.StandardButton.Cancel)
        confirmation.exec()
        if confirmation.clickedButton() == erase:
            self.run_job("Clear notebook memory", self.service.clear_device)

    def log(self, message: str) -> None:
        self.activity.append(message)
        self.footer.setText(message)
        self.footer.setToolTip(message)

    def closeEvent(self, event: Any) -> None:
        if self._busy:
            QMessageBox.information(self, "Operation in progress", "Let the current operation finish before closing HuionNote.")
            event.ignore()
            return
        if not self.resolve_editor():
            event.ignore()
            return
        if self._history_index < len(self._live_history):
            self.canvas.set_samples(self._current_live, self._current_colors)
            self.canvas.set_background(self._current_background)
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
