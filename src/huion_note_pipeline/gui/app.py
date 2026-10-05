"""Main GUI application for Huion Note Pipeline.

Spec source: huion-note-pipeline.allium — GUI surface.

Design: Notion-inspired light-mode with functional page routing.
  - Light sidebar (#F7F6F3) with active page navigation.
  - Two full pages: Live Canvas and Notes.
  - Connection status pill in the topbar (polls every 2s).
  - Status pills inline with note cards.
  - Monospace log strip at bottom.
"""
from __future__ import annotations

import asyncio
import math
import os
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Any, Callable, Tuple

from ..enums import NoteStatus, NoteCategory
from ..models import Note, ConversionResult, NoteFilename
from ..pipeline import SyncPipeline, NoteRegistry
from ..config import PipelineConfig
from ..converter import AntigravityBridge
from ..frontmatter import build_frontmatter, render_frontmatter
from ..editor import NoteEditorPage
from .. import htr as htr_module
from .components import ModernScrollbar, ModernModalDialog, ModernDropdownMenu, ModernSettingsDialog, ModernMarkdownViewerDialog
from .tray import HuionNoteTray
import sys
home_dir = str(Path.home())
if home_dir not in sys.path:
    sys.path.insert(0, home_dir)
from huion.sync_engine import OfflineSyncManager


# ── Palette (all light mode) ──────────────────────────────────────────────────

# Sidebar
SB_BG       = "#F7F6F3"   # same as page bg — seamless sidebar
SB_HOVER    = "#EBEBEA"
SB_ACTIVE   = "#E9E9E8"
SB_TEXT     = "#37352F"
SB_TEXT_DIM = "#9B9A97"
SB_SEP      = "#E3E2DE"
SB_WIDTH    = 208

# Main content
BG_MAIN     = "#FFFFFF"
BG_PAGE     = "#F7F6F3"
BG_CARD     = "#FFFFFF"
BG_CARD_HOV = "#F7F6F3"
BG_WELL     = "#EEEDE9"
BG_CANVAS   = "#F8F7F5"

# Text
TXT_PRI     = "#1F1E1A"
TXT_SEC     = "#6B6A67"
TXT_TER     = "#A8A6A3"
TXT_INV     = "#FFFFFF"

# Borders
BORD_SUB    = "#D8D7D3"
BORD_MED    = "#B8B7B3"

# Accent bars on note cards (left stripe per status)
STATUS_BAR = {
    NoteStatus.CONVERTED:  "#4CAF50",
    NoteStatus.CONVERTING: "#F5A623",
    NoteStatus.FAILED:     "#E53935",
    NoteStatus.SYNCED:     "#D3D1CB",
}

# Status pill (bg, fg, label)
STATUS_PILL = {
    NoteStatus.CONVERTED:  ("#E8F5E9", "#2E7D32", "Converted"),
    NoteStatus.CONVERTING: ("#FFF8E1", "#E65100", "Converting"),
    NoteStatus.FAILED:     ("#FFEBEE", "#C62828", "Failed  Retry"),
    NoteStatus.SYNCED:     ("#F1F1EF", "#787774", "Queued"),
}

# Connection pill colours
CONN_PILL = {
    True:  ("#E8F5E9", "#2E7D32", "Connected"),
    False: ("#F1F1EF", "#9B9A97", "Disconnected"),
    None:  ("#FFF8E1", "#E65100", "Connecting"),
}

FONT_UI   = "sans-serif"
FONT_MONO = "monospace"


def _f(size: int, bold: bool = False) -> tuple:
    return (FONT_UI, size, "bold") if bold else (FONT_UI, size)

def _fm(size: int) -> tuple:
    return (FONT_MONO, size)


# ── Reusable primitives ───────────────────────────────────────────────────────

class Separator(tk.Frame):
    def __init__(self, master, orient="h", color=BORD_SUB, **kw):
        if orient == "h":
            super().__init__(master, height=1, bg=color, **kw)
        else:
            super().__init__(master, width=1, bg=color, **kw)


class FlatButton(tk.Label):
    """Clickable label button with hover feedback — no border, no relief."""

    def __init__(self, master, text="", command=None,
                 bg=BG_MAIN, hover_bg=BG_WELL,
                 fg=TXT_PRI, padx=10, pady=5,
                 font=None, cursor="hand2", **kw):
        super().__init__(master, text=text, bg=bg, fg=fg,
                         font=font or _f(9), padx=padx, pady=pady,
                         cursor=cursor, **kw)
        self._bg = bg
        self._hbg = hover_bg
        self.bind("<Enter>", lambda _: self.config(bg=self._hbg))
        self.bind("<Leave>", lambda _: self.config(bg=self._bg))
        if command:
            self.bind("<Button-1>", lambda _: command())

    def set_colors(self, bg, hover_bg):
        self._bg = bg
        self._hbg = hover_bg
        self.config(bg=bg)


class PillLabel(tk.Label):
    """Compact inline status pill."""
    def __init__(self, master, text="", bg="#F1F1EF", fg=TXT_SEC, **kw):
        super().__init__(master, text=text, bg=bg, fg=fg,
                         font=_f(8, True), padx=7, pady=2, **kw)


class RoundedButton(tk.Canvas):
    """Modern pill-shaped button drawn on a Canvas for Tkinter (no ttk needed)."""

    def __init__(self, master, text="", command=None,
                 bg="#1F1E1A", fg="#FFFFFF",
                 hover_bg=None, radius=8,
                 padx=14, pady=5, font=None, **kw):
        self._text = text
        self._bg = bg
        self._fg = fg
        self._font = font or _f(8)
        self._command = command
        self._radius = int(radius)
        self._padx = int(padx)
        self._pady = int(pady)

        # Measure text dimensions reliably using tkinter.font
        import tkinter.font as tkfont
        fobj = tkfont.Font(font=self._font)
        tw = int(fobj.measure(text))
        th = int(fobj.metrics("linespace"))

        self._bw = int(tw + self._padx * 2)
        self._bh = int(th + self._pady * 2)

        self._hover_bg = hover_bg or self._darken(bg)

        # Determine parent background for canvas transparency
        try:
            parent_bg = master.cget("bg")
        except Exception:
            parent_bg = "#FFFFFF"

        super().__init__(master, width=self._bw, height=self._bh,
                         bg=parent_bg, highlightthickness=0, bd=0,
                         cursor="hand2", **kw)
        self._draw(self._bg)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _darken(self, hex_color: str) -> str:
        try:
            h = hex_color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            factor = 0.80
            r = max(0, int(r * factor))
            g = max(0, int(g * factor))
            b = max(0, int(b * factor))
            return f"#{r:02X}{g:02X}{b:02X}"
        except Exception:
            return hex_color

    def _draw(self, fill: str) -> None:
        self.delete("all")
        w, h, r = self._bw, self._bh, self._radius
        # Rounded rectangle composed of arcs + rectangles
        self.create_arc(0,     0,     r*2, r*2, start=90,  extent=90, fill=fill, outline=fill)
        self.create_arc(w-r*2, 0,     w,   r*2, start=0,   extent=90, fill=fill, outline=fill)
        self.create_arc(0,     h-r*2, r*2, h,   start=180, extent=90, fill=fill, outline=fill)
        self.create_arc(w-r*2, h-r*2, w,   h,   start=270, extent=90, fill=fill, outline=fill)
        self.create_rectangle(r, 0,   w-r, h,   fill=fill, outline=fill)
        self.create_rectangle(0, r,   w,   h-r, fill=fill, outline=fill)
        self.create_text(w // 2, h // 2, text=self._text,
                         fill=self._fg, font=self._font, anchor="center")

    def _on_enter(self, _=None):  self._draw(self._hover_bg)
    def _on_leave(self, _=None):  self._draw(self._bg)
    def _on_click(self, _=None):  self._draw(self._darken(self._hover_bg))

    def _on_release(self, _=None):
        self._draw(self._hover_bg)
        if self._command:
            self._command()



class NavItem(tk.Frame):
    """A sidebar navigation row: icon + label, toggles active state."""

    def __init__(self, master, icon: str, label: str, active=False,
                 command=None, **kw):
        super().__init__(master, bg=SB_ACTIVE if active else SB_BG,
                         cursor="hand2", **kw)
        self._active = active
        self._cmd = command
        self._icon = tk.Label(self, text=icon, bg=self["bg"],
                              fg=TXT_PRI, font=_f(10), padx=12, pady=6)
        self._icon.pack(side=tk.LEFT)
        self._lbl = tk.Label(self, text=label, bg=self["bg"],
                             fg=TXT_PRI if active else TXT_SEC,
                             font=_f(9, active), anchor="w")
        self._lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=6)
        self.bind("<Button-1>", self._on_click)
        self._icon.bind("<Button-1>", self._on_click)
        self._lbl.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._hover_on)
        self.bind("<Leave>", self._hover_off)
        self._icon.bind("<Enter>", self._hover_on)
        self._icon.bind("<Leave>", self._hover_off)
        self._lbl.bind("<Enter>", self._hover_on)
        self._lbl.bind("<Leave>", self._hover_off)

    def set_active(self, active: bool):
        self._active = active
        bg = SB_ACTIVE if active else SB_BG
        self.config(bg=bg)
        self._icon.config(bg=bg)
        self._lbl.config(bg=bg, fg=TXT_PRI if active else TXT_SEC,
                         font=_f(9, active))

    def _hover_on(self, _=None):
        if not self._active:
            for w in (self, self._icon, self._lbl):
                w.config(bg=SB_HOVER)

    def _hover_off(self, _=None):
        bg = SB_ACTIVE if self._active else SB_BG
        for w in (self, self._icon, self._lbl):
            w.config(bg=bg)

    def _on_click(self, _=None):
        if self._cmd:
            self._cmd()


# ── SVG thumbnail canvas ──────────────────────────────────────────────────────

class SvgThumbnailCanvas(tk.Canvas):
    def __init__(self, master, width=80, height=108, **kw):
        super().__init__(master, width=width, height=height,
                         bg="#F8F7F5", highlightthickness=1,
                         highlightbackground="#D0CFC9", **kw)
        self.w, self.h = width, height

    def load_svg(self, svg_path: Optional[str]) -> None:
        self.delete("all")
        if not svg_path or not Path(svg_path).exists():
            self.create_text(self.w // 2, self.h // 2,
                             text="No preview", fill=TXT_TER, font=_f(7))
            return
        try:
            content = Path(svg_path).read_text(encoding="utf-8", errors="ignore")
            wm = re.search(r'width="([0-9.]+)"', content)
            hm = re.search(r'height="([0-9.]+)"', content)
            ow = float(wm.group(1)) if wm else 900.0
            oh = float(hm.group(1)) if hm else 1190.0
            scale = min((self.w - 8) / ow, (self.h - 8) / oh)
            ox = (self.w - ow * scale) / 2
            oy = (self.h - oh * scale) / 2
            self.create_rectangle(2, 2, self.w-2, self.h-2,
                                  outline="#D8D7D3", fill="#F8F7F5")
            for d in re.findall(r'd="([^"]+)"', content):
                pts = re.findall(r'([0-9.]+),([0-9.]+)', d)
                if len(pts) >= 2:
                    coords = []
                    for xs, ys in pts:
                        coords += [ox + float(xs)*scale, oy + float(ys)*scale]
                    self.create_line(coords, fill="#2A2A2A", width=1.0,
                                     smooth=True, capstyle=tk.ROUND)
                elif len(pts) == 1:
                    cx = ox + float(pts[0][0]) * scale
                    cy = oy + float(pts[0][1]) * scale
                    self.create_oval(cx-.8, cy-.8, cx+.8, cy+.8,
                                     fill="#2A2A2A", outline="")
        except Exception:
            self.create_text(self.w//2, self.h//2,
                             text="Error", fill=TXT_TER, font=_f(7))


# ── Note card ─────────────────────────────────────────────────────────────────

class NoteCard(tk.Frame):
    def __init__(self, master, note: Note,
                 on_retry: Optional[Callable[[Note], None]] = None,
                 on_edit: Optional[Callable[[Note], None]] = None,
                 on_convert_ocr: Optional[Callable[[Note], None]] = None,
                 on_convert_ai: Optional[Callable[[Note], None]] = None,
                 on_view_md: Optional[Callable[[Note, str], None]] = None,
                 **kw):
        super().__init__(master, bg=BG_CARD,
                         highlightthickness=1,
                         highlightbackground="#D0CFC9",
                         relief=tk.FLAT, **kw)
        self.note = note
        self.on_retry = on_retry
        self.on_edit = on_edit
        self.on_convert_ocr = on_convert_ocr
        self.on_convert_ai = on_convert_ai
        self.on_view_md = on_view_md
        self._build()
        self._bind_hover(self)

    def _bind_hover(self, w):
        w.bind("<Enter>", self._hover_on)
        w.bind("<Leave>", self._hover_off)
        for child in w.winfo_children():
            self._bind_hover(child)

    def _hover_on(self, _=None):
        self.config(highlightbackground="#A8A6A0")
        self._set_bg(BG_CARD_HOV)

    def _hover_off(self, _=None):
        self.config(highlightbackground="#D0CFC9")
        self._set_bg(BG_CARD)

    def _set_bg(self, c):
        try:
            self.config(bg=c)
        except Exception:
            pass
        for w in self.winfo_children():
            try:
                w.config(bg=c)
            except Exception:
                pass

    def _get_md_path(self) -> Optional[str]:
        if getattr(self.note, "markdown_path", None) and Path(self.note.markdown_path).exists():
            return self.note.markdown_path
        if self.note.svg_path:
            p = Path(self.note.svg_path)
            # Direct sibling .md
            cand = p.with_suffix(".md")
            if cand.exists():
                return str(cand.resolve())
            # In markdown/ sibling folder
            cand2 = p.parent / "markdown" / f"{p.stem}.md"
            if cand2.exists():
                return str(cand2.resolve())
        return None

    def _build(self):
        accent = STATUS_BAR.get(self.note.status, "#D3D1CB")
        # Left colour stripe
        tk.Frame(self, width=3, bg=accent).pack(side=tk.LEFT, fill=tk.Y)

        inner = tk.Frame(self, bg=BG_CARD, padx=12, pady=10)
        inner.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner.columnconfigure(1, weight=1)

        # Thumbnail
        thumb = SvgThumbnailCanvas(inner, width=74, height=100)
        thumb.grid(row=0, column=0, rowspan=4, padx=(0, 12), sticky="nw")
        thumb.load_svg(self.note.svg_path)

        # Title
        tk.Label(inner, text=self._title(),
                 font=_f(10, True), bg=BG_CARD, fg=TXT_PRI,
                 anchor="w").grid(row=0, column=1, sticky="ew", pady=(2, 2))

        # Meta
        parts = []
        if self.note.synced_at:
            parts.append(self.note.synced_at.strftime("%b %-d, %Y  %H:%M"))
        if self.note.category:
            cat_val = self.note.category.value if hasattr(self.note.category, "value") else str(self.note.category)
            if cat_val != NoteCategory.UNCLASSIFIED.value:
                parts.append(cat_val.title())
        tk.Label(inner, text="  ·  ".join(parts) if parts else "Pending",
                 font=_f(8), bg=BG_CARD, fg=TXT_SEC,
                 anchor="w").grid(row=1, column=1, sticky="ew", pady=(0, 4))

        # Tags
        tags = getattr(self.note, "tags", None)
        if tags:
            row = tk.Frame(inner, bg=BG_CARD)
            row.grid(row=2, column=1, sticky="w")
            for t in tags[:4]:
                tk.Label(row, text=f"#{t}", font=_f(7),
                         bg=BG_WELL, fg=TXT_SEC,
                         padx=5, pady=1).pack(side=tk.LEFT, padx=(0, 4))

        # ── Action row: Edit | OCR | AI Convert | View MD | status pill ────────
        action_row = tk.Frame(inner, bg=BG_CARD)
        action_row.grid(row=3, column=1, sticky="w", pady=(6, 0))

        if self.on_edit:
            RoundedButton(
                action_row, text="Edit", radius=6,
                bg=BG_WELL, fg=TXT_PRI, padx=10, pady=3,
                font=_f(8),
                command=lambda: self.on_edit(self.note),
            ).pack(side=tk.LEFT, padx=(0, 5))

        if self.on_convert_ocr:
            RoundedButton(
                action_row, text="OCR (Local)", radius=6,
                bg="#EFF6FF", fg="#1D4ED8", padx=10, pady=3,
                font=_f(8),
                command=lambda: self.on_convert_ocr(self.note),
            ).pack(side=tk.LEFT, padx=(0, 5))

        if self.on_convert_ai:
            RoundedButton(
                action_row, text="AI Convert (Gemini)", radius=6,
                bg="#F5F3FF", fg="#6D28D9", padx=10, pady=3,
                font=_f(8),
                command=lambda: self.on_convert_ai(self.note),
            ).pack(side=tk.LEFT, padx=(0, 5))

        md_path = self._get_md_path()
        if md_path and self.on_view_md:
            RoundedButton(
                action_row, text="View Markdown", radius=6,
                bg="#ECFDF5", fg="#059669", padx=10, pady=3,
                font=_f(8, True),
                command=lambda p=md_path: self.on_view_md(self.note, p),
            ).pack(side=tk.LEFT, padx=(0, 5))

        # Status pill (top-right)
        pbg, pfg, ptxt = STATUS_PILL.get(
            self.note.status, ("#F1F1EF", "#787774", ""))
        pill = tk.Label(inner, text=ptxt, font=_f(7, True),
                        bg=pbg, fg=pfg, padx=7, pady=2)
        pill.grid(row=0, column=2, sticky="ne", padx=(8, 0))
        if self.note.status == NoteStatus.FAILED and self.on_retry:
            pill.config(cursor="hand2")
            pill.bind("<Button-1>", lambda _: self.on_retry(self.note))

    def _title(self) -> str:
        if self.note.filename:
            return self.note.filename.title_part.replace("_", " ").title()
        if hasattr(self.note, "title") and getattr(self.note, "title"):
            return getattr(self.note, "title")
        if self.note.svg_path:
            return Path(self.note.svg_path).stem.replace("_", " ").title()
        return "Untitled Page"


# ── Main application ──────────────────────────────────────────────────────────

class HuionNotePipelineApp:
    """
    Two-page app:
      PAGE_LIVE   — full-page live drawing canvas
      PAGE_NOTES  — full-page synced notes browser
    Sidebar nav switches between them.
    Topbar shows page title + connection pill + contextual actions.
    """

    PAGE_LIVE   = "live"
    PAGE_NOTES  = "notes"
    PAGE_EDITOR = "editor"

    PAGE_WIDTH  = 28200
    PAGE_HEIGHT = 37400

    def __init__(
        self,
        pipeline: Optional[SyncPipeline] = None,
        registry: Optional[NoteRegistry] = None,
        config: Optional[PipelineConfig] = None,
        bridge: Optional[Any] = None,
        device: Optional[Any] = None,
    ) -> None:
        self.pipeline  = pipeline
        self.registry  = registry or (pipeline.registry if pipeline else NoteRegistry())
        self.config    = config or (pipeline.config if pipeline else PipelineConfig(output_directory="./notes_output"))
        self.bridge    = bridge
        self.device    = device
        self.root: Optional[tk.Tk] = None
        self._ui_queue: queue.Queue = queue.Queue()

        self._converter        = AntigravityBridge()
        self._live_pts: List[Tuple[float, float, int]] = []
        
        self._sync_active      = False
        self._htr_active       = False
        self._current_page     = self.PAGE_LIVE
        self._conn_state: Optional[bool] = None
        self._tray: Optional[HuionNoteTray] = None
        self.show_log: bool    = False
        self._statusbar: Optional[tk.Frame] = None

        # Page frame references (built lazily)
        self._live_frame:   Optional[tk.Frame] = None
        self._notes_frame:  Optional[tk.Frame] = None
        self._editor_frame: Optional[NoteEditorPage] = None
        self._nav_items:    dict = {}            # page_id -> NavItem
        self._editing_note: Optional[Note] = None  # note open in editor

    def call_on_ui(self, fn: Callable[[], None]) -> None:
        """Enqueue a callable to be executed on the Tkinter main loop."""
        self._ui_queue.put(fn)

    # ── Connection status polling ─────────────────────────────────────────────

    def _poll_connection(self) -> None:
        """Check bridge thread liveness & connection state every 2 s and update the pill."""
        if not self.root:
            return
        if self.bridge:
            alive = bool(getattr(self.bridge, "_stream_thread", None)
                         and self.bridge._stream_thread.is_alive())
            is_conn = bool(alive and getattr(self.bridge, "_is_connected", False))
            if is_conn:
                state = True
            elif alive:
                state = None  # Thread is alive, connecting or reconnecting
            else:
                state = False
                # Auto-reconnect if stream thread stopped unexpectedly
                mac = "25:6C:BB:8D:19:50"
                self.bridge.stream_pen_input(mac)
        else:
            state = False

        self._conn_state = state
        self._update_conn_pill()

        batt = getattr(self.bridge, "_last_battery", None) if self.bridge else None
        if hasattr(self, "_tray") and self._tray:
            self._tray.update_status(self._conn_state, batt)

        try:
            self.root.after(2000, self._poll_connection)
        except Exception:
            pass

    def _update_conn_pill(self) -> None:
        if not hasattr(self, "_conn_pill"):
            return
        bg, fg, txt = CONN_PILL.get(self._conn_state, CONN_PILL[False])
        dot = "\u2022"

        # Append battery % if connected and available
        batt_str = ""
        if self._conn_state is True and self.bridge:
            batt = getattr(self.bridge, "_last_battery", None)
            if batt is not None:
                batt_str = f"  \u2014  {batt}%"

        label = f"{dot}  {txt}{batt_str}"
        self._conn_pill.config(text=label, bg=bg, fg=fg)

        # Mirror to sidebar pill
        if hasattr(self, "_conn_pill_sb"):
            self._conn_pill_sb.config(text=label, bg=bg, fg=fg)

    # ── Inking & A5 Page helpers ──────────────────────────────────────────────

    A5_RATIO = 148.0 / 210.0  # 0.70476 (Standard A5 aspect ratio)

    def _get_a5_page_rect(self) -> Tuple[float, float, float, float]:
        """Return (x0, y0, w, h) of the centered A5 paper sheet on the canvas."""
        if not getattr(self, "live_canvas", None):
            return 20.0, 20.0, 460.0, 650.0
        cw = self.live_canvas.winfo_width() or 500
        ch = self.live_canvas.winfo_height() or 700
        pad = 20

        avail_w = max(10, cw - pad * 2)
        avail_h = max(10, ch - pad * 2)

        if avail_w / avail_h > self.A5_RATIO:
            page_h = avail_h
            page_w = page_h * self.A5_RATIO
        else:
            page_w = avail_w
            page_h = page_w / self.A5_RATIO

        x0 = (cw - page_w) / 2.0
        y0 = (ch - page_h) / 2.0
        return x0, y0, page_w, page_h

    def _canvas_xy(self, pt: Any) -> Tuple[float, float]:
        x0, y0, pw, ph = self._get_a5_page_rect()
        cx = x0 + (pt.x / self.PAGE_WIDTH) * pw
        cy = y0 + (pt.y / self.PAGE_HEIGHT) * ph
        return cx, cy

    def _pen_width(self, pressure: int) -> float:
        p = min(1.0, max(0.0, pressure / 8192.0))
        return 0.8 + p * 1.8

    def _draw_stroke_segment(self, coords: list, width: float) -> None:
        if len(coords) < 4:
            return
        self.live_canvas.create_line(
            *coords,
            fill="#1C1C1C",
            width=width,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
            smooth=True,
            splinesteps=36,
        )

    def _on_live_pen_point(self, point: Any) -> None:
        if not self.root:
            return

        def _draw():
            # If Note Editor is active, route pen strokes into the editor
            if self._current_page == self.PAGE_EDITOR and self._editor_frame:
                self._editor_frame.on_pen_point(point)
                return

            if not getattr(self, "live_canvas", None):
                return

            if point.touch or point.pressure > 0:
                tx, ty = self._canvas_xy(point)
                self._live_pts.append((tx, ty, point.pressure))
                n = len(self._live_pts)

                if n < 2:
                    return

                p0, p1 = self._live_pts[-2], self._live_pts[-1]
                dx, dy = p1[0] - p0[0], p1[1] - p0[1]
                if (dx * dx + dy * dy) < 0.2 and n > 2:
                    return

                pw = self._pen_width(p1[2])

                if n == 2:
                    self._draw_stroke_segment([p0[0], p0[1], p1[0], p1[1]], pw)
                else:
                    pp = self._live_pts[-3]
                    mx0 = (pp[0] + p0[0]) / 2.0
                    my0 = (pp[1] + p0[1]) / 2.0
                    mx1 = (p0[0] + p1[0]) / 2.0
                    my1 = (p0[1] + p1[1]) / 2.0
                    self._draw_stroke_segment([mx0, my0, p0[0], p0[1], mx1, my1], pw)
            else:
                self._live_pts.clear()

        try:
            self.root.after(0, _draw)
        except Exception:
            pass

    def handle_hardware_button(self) -> None:
        def _act():
            if getattr(self, "live_canvas", None):
                self.live_canvas.delete("all")
                self._draw_dot_grid()
            self._live_pts.clear()
            self.log("[Hardware] Page button — canvas cleared.")
        if self.root:
            self.root.after(0, _act)

    def _draw_dot_grid(self) -> None:
        self.live_canvas.delete("grid")
        self.live_canvas.delete("paper")
        x0, y0, pw, ph = self._get_a5_page_rect()

        # Paper drop shadow (offset 4px right/down, soft grey)
        self.live_canvas.create_rectangle(
            x0 + 4, y0 + 4, x0 + pw + 4, y0 + ph + 4,
            fill="#D4D3CF", outline="", tags="paper"
        )

        # White A5 paper surface with crisp 1px border
        self.live_canvas.create_rectangle(
            x0, y0, x0 + pw, y0 + ph,
            fill="#FFFFFF", outline="#C8C7C3", width=1,
            tags="paper"
        )
        self.live_canvas.tag_lower("paper")

        # Subtle Notion dot grid inside the A5 page
        step = 24
        for x in range(int(x0) + step, int(x0 + pw), step):
            for y in range(int(y0) + step, int(y0 + ph), step):
                self.live_canvas.create_oval(
                    x - 0.8, y - 0.8, x + 0.8, y + 0.8,
                    fill="#C4C2BE", outline="", tags="grid"
                )

    def _bring_to_front(self) -> None:
        """Bring window to foreground when clicked from system tray."""
        if self.root:
            def _show():
                try:
                    self.root.deiconify()
                    self.root.lift()
                    self.root.focus_force()
                except Exception:
                    pass
            self.call_on_ui(_show)

    # ── Window builder ────────────────────────────────────────────────────────

    def build_window(self) -> tk.Tk:
        root = tk.Tk(className="huionnote")
        root.title("HuionNote")
        root.geometry("1140x720")
        root.configure(bg=SB_BG)
        root.minsize(860, 540)
        self.root = root

        # Set application icon photo
        icon_path = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "huionnote.png"
        if not icon_path.exists():
            icon_path = Path(__file__).resolve().parent.parent.parent / "assets" / "huionnote.png"
        if icon_path.exists():
            try:
                icon_img = tk.PhotoImage(file=str(icon_path))
                root.iconphoto(True, icon_img)
                self._icon_img_ref = icon_img
            except Exception:
                pass

        # Start background system tray indicator
        self._tray = HuionNoteTray(
            on_show=self._bring_to_front,
            on_sync=self.handle_sync_now,
            on_quit=self._on_close,
        )
        self._tray.start()

        # ── Outer shell: sidebar | content ───────────────────────────────────
        shell = tk.Frame(root, bg=SB_BG)
        shell.pack(fill=tk.BOTH, expand=True)

        # Sidebar
        self._sidebar = tk.Frame(shell, bg=SB_BG, width=SB_WIDTH)
        self._sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self._sidebar.pack_propagate(False)
        self._build_sidebar(self._sidebar)

        # Sidebar separator
        Separator(shell, orient="v", color=BORD_SUB).pack(side=tk.LEFT, fill=tk.Y)

        # Content area (topbar + page stack)
        self._content_shell = tk.Frame(shell, bg=BG_MAIN)
        self._content_shell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Topbar (persistent across pages)
        self._topbar = tk.Frame(self._content_shell, bg=BG_MAIN, pady=0)
        self._topbar.pack(fill=tk.X, side=tk.TOP)
        self._build_topbar(self._topbar)

        Separator(self._content_shell).pack(fill=tk.X)

        # Page container — frames stacked, only one visible at a time
        self._page_stack = tk.Frame(self._content_shell, bg=BG_PAGE)
        self._page_stack.pack(fill=tk.BOTH, expand=True)

        self._live_frame  = self._build_live_page(self._page_stack)
        self._notes_frame = self._build_notes_page(self._page_stack)

        # Status bar at very bottom of root
        self._build_statusbar(root)

        # Wire close protocol so BLE connection is maintained until window is closed
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Wire bridge
        if self.bridge:
            self.bridge.on_pen_point(self._on_live_pen_point)
            self.bridge.on_hardware_button(self.handle_hardware_button)
            alive = bool(getattr(self.bridge, "_stream_thread", None)
                         and self.bridge._stream_thread.is_alive())
            if not alive:
                mac = "25:6C:BB:8D:19:50"
                self.bridge.stream_pen_input(mac)

        # Show default page
        self._show_page(self.PAGE_LIVE)

        # UI Queue processor (thread-safe dispatcher)
        def _process_ui_queue():
            while not self._ui_queue.empty():
                try:
                    fn = self._ui_queue.get_nowait()
                    fn()
                except Exception:
                    pass
            if self.root:
                try:
                    self.root.after(50, _process_ui_queue)
                except Exception:
                    pass

        self.root.after(50, _process_ui_queue)

        # Start connection polling
        self.root.after(500, self._poll_connection)

        # Index all documents on disk into Library
        self.load_library()
        return root

    # ── Library Management ───────────────────────────────────────────────────

    def load_library(self) -> None:
        """Scan all standard storage locations and index all SVG and Markdown notes."""
        search_dirs = [
            getattr(self.config, "output_directory", "./notes_output"),
            os.path.expanduser("~/HuionNotes"),
            "./notes_output",
            "./notes_output/personal",
            "./notes_output/work",
            "./exported_notes",
        ]
        self.registry.load_from_disk(search_dirs)
        self.call_on_ui(self.refresh_notes_list)
        total = len(self.registry.all())
        self.log(f"[Library] {total} documents indexed across storage locations.")

    # ── Connection Reconnect & Settings ──────────────────────────────────────

    def handle_retry_connection(self, mac: str = "25:6C:BB:8D:19:50") -> None:
        """Manually trigger a clean reconnection to the Huion Note X10."""
        self._conn_state = None
        self._update_conn_pill()
        self.log(f"[BLE] Retrying connection to {mac}...")

        def _worker():
            if self.bridge:
                self.bridge.retry_connection(mac)

        threading.Thread(target=_worker, daemon=True).start()

    def open_settings(self) -> None:
        """Open the modern Settings dialog."""
        ModernSettingsDialog(
            parent=self.root,
            mac_address="25:6C:BB:8D:19:50",
            is_connected=self._conn_state,
            battery=getattr(self.bridge, "_last_battery", None) if self.bridge else None,
            total_notes_count=len(self.registry.all()),
            show_log=self.show_log,
            on_retry_connect=self.handle_retry_connection,
            on_rescan_library=self.load_library,
            on_save_gemini_key=self._save_gemini_key,
            on_toggle_log=self.set_log_visible,
        )

    def _save_gemini_key(self, key: str) -> None:
        os.environ["GEMINI_API_KEY"] = key
        self.log("[Settings] Gemini API key saved.")

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self, parent: tk.Frame) -> None:
        # App title
        hdr = tk.Frame(parent, bg=SB_BG, padx=14, pady=14)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="HuionNote", font=_f(11, True),
                 bg=SB_BG, fg=TXT_PRI, anchor="w").pack(fill=tk.X)
        tk.Label(hdr, text="X10 Digital Notebook", font=_f(8),
                 bg=SB_BG, fg=TXT_SEC, anchor="w").pack(fill=tk.X)

        Separator(parent, color=BORD_SUB).pack(fill=tk.X, pady=4)

        # Navigation
        nav_defs = [
            ("live_canvas",    "Live Canvas",      self.PAGE_LIVE),
            ("synced_notes",   "Document Library", self.PAGE_NOTES),
        ]
        for key, label, page in nav_defs:
            item = NavItem(
                parent, icon="\u25CB", label=label,
                active=(page == self._current_page),
                command=lambda p=page: self._show_page(p),
            )
            item.pack(fill=tk.X, padx=6, pady=1)
            self._nav_items[page] = item

        Separator(parent, color=BORD_SUB).pack(fill=tk.X, pady=8)

        # Device section
        tk.Label(parent, text="DEVICE", font=_fm(7),
                 bg=SB_BG, fg=TXT_TER, padx=14, pady=4).pack(fill=tk.X, anchor="w")

        # Connection pill in sidebar
        conn_bg, conn_fg, conn_txt = CONN_PILL[False]
        self._conn_pill_sb = tk.Label(
            parent, text=f"\u2022  Disconnected",
            font=_f(8), bg=conn_bg, fg=conn_fg,
            padx=10, pady=4, anchor="w", cursor="hand2",
        )
        self._conn_pill_sb.pack(fill=tk.X, padx=10, pady=2)
        self._conn_pill_sb.bind("<Button-1>", lambda _: self.handle_retry_connection())

        FlatButton(
            parent, text="Retry Connection",
            bg=SB_BG, hover_bg=SB_HOVER,
            fg=TXT_PRI, font=_f(8, True),
            padx=14, pady=5, anchor="w",
            command=self.handle_retry_connection,
        ).pack(fill=tk.X, padx=6, pady=(2, 0))

        FlatButton(
            parent, text="Sync Now",
            bg=SB_BG, hover_bg=SB_HOVER,
            fg=TXT_SEC, font=_f(9),
            padx=14, pady=5, anchor="w",
            command=self.handle_sync_now,
        ).pack(fill=tk.X, padx=6)

        # Bottom section: Settings + version
        bottom_box = tk.Frame(parent, bg=SB_BG)
        bottom_box.pack(side=tk.BOTTOM, fill=tk.X, pady=8)

        FlatButton(
            bottom_box, text="⚙  Settings",
            bg=SB_BG, hover_bg=SB_HOVER,
            fg=TXT_PRI, font=_f(9),
            padx=14, pady=6, anchor="w",
            command=self.open_settings,
        ).pack(fill=tk.X, padx=6)

        tk.Label(bottom_box, text="v1.0.0", font=_f(7),
                 bg=SB_BG, fg=TXT_TER).pack(pady=(4, 0))

    # ── Topbar ────────────────────────────────────────────────────────────────

    def _build_topbar(self, parent: tk.Frame) -> None:
        parent.columnconfigure(1, weight=1)

        # Page title (updates on navigation)
        self._topbar_title = tk.Label(
            parent, text="Live Canvas",
            font=_f(11, True), bg=BG_MAIN, fg=TXT_PRI,
            padx=20, pady=12,
        )
        self._topbar_title.pack(side=tk.LEFT)

        # Right side: connection pill + contextual actions
        right = tk.Frame(parent, bg=BG_MAIN)
        right.pack(side=tk.RIGHT, padx=16, pady=8)

        # Connection status pill
        conn_bg, conn_fg, conn_txt = CONN_PILL[False]
        self._conn_pill = tk.Label(
            right, text="\u2022  Disconnected",
            font=_f(8, True), bg=conn_bg, fg=conn_fg,
            padx=8, pady=3, cursor="hand2",
        )
        self._conn_pill.pack(side=tk.LEFT, padx=(0, 10))
        self._conn_pill.bind("<Button-1>", lambda _: self.handle_retry_connection())

        # Contextual action buttons (visibility toggled per page)
        self._btn_clear = FlatButton(
            right, text="Clear Canvas",
            bg=BG_MAIN, hover_bg=BG_WELL,
            fg=TXT_SEC, font=_f(9),
            padx=10, pady=4,
            command=self._clear_canvas,
        )
        self._btn_rescan = FlatButton(
            right, text="Rescan Library",
            bg=BG_MAIN, hover_bg=BG_WELL,
            fg=TXT_SEC, font=_f(9),
            padx=10, pady=4,
            command=self.load_library,
        )
        self._btn_sync = RoundedButton(
            right, text="Sync Now",
            bg=TXT_PRI, fg=TXT_INV,
            radius=7, padx=14, pady=4,
            font=_f(9, True),
            command=self.handle_sync_now,
        )

        self._clear_menu = ModernDropdownMenu(parent)
        self._clear_menu.add_option("Clear Synced Pages", self.handle_clear_synced)
        self._clear_menu.add_option("Clear All Pages from Device", self.handle_clear_all, is_danger=True)

        self._btn_clear_mem = FlatButton(
            right, text="Clear Memory  ▾",
            bg=BG_MAIN, hover_bg=BG_WELL,
            fg=TXT_SEC, font=_f(9),
            padx=10, pady=4,
            command=lambda: self._clear_menu.show(self._btn_clear_mem),
        )

    def _update_topbar_for_page(self, page: str) -> None:
        titles = {
            self.PAGE_LIVE:   "Live Canvas",
            self.PAGE_NOTES:  "Document Library",
            self.PAGE_EDITOR: "Note Editor",
        }
        self._topbar_title.config(text=titles.get(page, ""))

        # Hide all contextual buttons first
        self._btn_clear.pack_forget()
        self._btn_rescan.pack_forget()
        self._btn_sync.pack_forget()
        self._btn_clear_mem.pack_forget()

        if page == self.PAGE_LIVE:
            self._btn_clear.pack(side=tk.LEFT, padx=(0, 4))
            self._btn_sync.pack(side=tk.LEFT)
        elif page == self.PAGE_NOTES:
            self._btn_rescan.pack(side=tk.LEFT, padx=(0, 4))
            self._btn_clear_mem.pack(side=tk.LEFT, padx=(0, 6))
            self._btn_sync.pack(side=tk.LEFT)
        # PAGE_EDITOR: editor has its own toolbar, no topbar buttons needed

    # ── Page switching ────────────────────────────────────────────────────────

    def _show_page(self, page: str) -> None:
        self._current_page = page

        # Toggle nav items (editor doesn't have a nav item — no highlight change)
        for pg, item in self._nav_items.items():
            item.set_active(pg == page)

        # Swap visible frames
        for pg, frame in [
            (self.PAGE_LIVE,   self._live_frame),
            (self.PAGE_NOTES,  self._notes_frame),
            (self.PAGE_EDITOR, self._editor_frame),
        ]:
            if frame:
                if page == pg:
                    frame.pack(fill=tk.BOTH, expand=True)
                else:
                    frame.pack_forget()

        # Editor page is cleaned up when navigating away
        if page != self.PAGE_EDITOR and self._editor_frame:
            self._editor_frame.pack_forget()
            self._editor_frame.destroy()
            self._editor_frame = None

        self._update_topbar_for_page(page)

    # ── Live Canvas page ──────────────────────────────────────────────────────

    def _build_live_page(self, parent: tk.Frame) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG_PAGE)

        self.live_canvas = tk.Canvas(
            frame, bg=BG_CANVAS, highlightthickness=0,
            cursor="crosshair",
        )
        self.live_canvas.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        self.live_canvas.bind("<Configure>", lambda _: self._draw_dot_grid())

        # Floating toolbar at bottom of canvas
        canvas_bar = tk.Frame(frame, bg=BG_MAIN, pady=0)
        canvas_bar.pack(fill=tk.X, side=tk.BOTTOM)
        Separator(canvas_bar).pack(fill=tk.X)
        inner_bar = tk.Frame(canvas_bar, bg=BG_MAIN, pady=6, padx=16)
        inner_bar.pack(fill=tk.X)

        tk.Label(inner_bar, text="Pen approach activates blue LED on device",
                 font=_f(8), bg=BG_MAIN, fg=TXT_TER).pack(side=tk.LEFT)

        FlatButton(
            inner_bar, text="Export SVG",
            bg=BG_MAIN, hover_bg=BG_WELL,
            fg=TXT_SEC, font=_f(8),
            padx=8, pady=3,
            command=self._export_live_svg,
        ).pack(side=tk.RIGHT)

        return frame

    def _clear_canvas(self) -> None:
        self.live_canvas.delete("all")
        self._draw_dot_grid()
        self._live_pts.clear()
        self.log("[Canvas] Cleared.")

    def _export_live_svg(self) -> None:
        """Export current live canvas strokes to an SVG file."""
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".svg",
            filetypes=[("SVG files", "*.svg"), ("All files", "*.*")],
            title="Export Live Canvas as SVG",
        )
        if not path:
            return
        w = self.live_canvas.winfo_width() or 500
        h = self.live_canvas.winfo_height() or 700
        lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">']
        for item in self.live_canvas.find_all():
            if self.live_canvas.type(item) in ("line",):
                coords = self.live_canvas.coords(item)
                if len(coords) >= 4:
                    pts_str = " ".join(f"{x},{y}" for x, y in zip(coords[::2], coords[1::2]))
                    lines.append(f'  <polyline points="{pts_str}" stroke="#1A1A1A" stroke-width="1.5" fill="none" stroke-linecap="round"/>')
        lines.append("</svg>")
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
            self.log(f"[Export] Saved live canvas to {path}")
        except Exception as e:
            self.log(f"[Export Error] {e}")

    # ── Notes page ────────────────────────────────────────────────────────────

    def _build_notes_page(self, parent: tk.Frame) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG_PAGE)

        # Filter chip bar
        filter_bar = tk.Frame(frame, bg=BG_MAIN, padx=20, pady=8)
        filter_bar.pack(fill=tk.X)

        self._filter_var = tk.StringVar(value="All")
        self._filter_chips: dict = {}
        for label in ("All", "Queued", "Converted", "Failed"):
            chip = tk.Label(
                filter_bar, text=label, font=_f(8),
                bg=BG_WELL, fg=TXT_SEC,
                padx=11, pady=4, cursor="hand2",
            )
            chip.pack(side=tk.LEFT, padx=(0, 6))

            def _chip_enter(c, l):
                if self._filter_var.get() != l:
                    c.configure(bg="#E5E5E2", fg=TXT_PRI)

            def _chip_leave(c, l):
                if self._filter_var.get() != l:
                    c.configure(bg=BG_WELL, fg=TXT_SEC)

            chip.bind("<Enter>", lambda _, c=chip, l=label: _chip_enter(c, l))
            chip.bind("<Leave>", lambda _, c=chip, l=label: _chip_leave(c, l))
            chip.bind("<Button-1>", lambda _, l=label: self._set_filter(l))
            self._filter_chips[label] = chip

        self._set_filter("All", refresh=False)

        Separator(frame).pack(fill=tk.X)

        # Stats bar
        self._stats_lbl = tk.Label(
            frame, text="", font=_f(8),
            bg=BG_PAGE, fg=TXT_TER, padx=20, pady=6, anchor="w",
        )
        self._stats_lbl.pack(fill=tk.X)

        # Scrollable cards
        list_wrap = tk.Frame(frame, bg=BG_PAGE)
        list_wrap.pack(fill=tk.BOTH, expand=True)

        self.cards_canvas = tk.Canvas(list_wrap, bg=BG_PAGE, highlightthickness=0)
        self.scrollable_cards = tk.Frame(self.cards_canvas, bg=BG_PAGE)

        self.scrollable_cards.bind(
            "<Configure>",
            lambda _: self.cards_canvas.configure(
                scrollregion=self.cards_canvas.bbox("all")),
        )
        self._cards_win = self.cards_canvas.create_window(
            (0, 0), window=self.scrollable_cards, anchor="nw")
        self.cards_canvas.bind(
            "<Configure>",
            lambda e: self.cards_canvas.itemconfig(self._cards_win, width=e.width))

        self.scrollbar = ModernScrollbar(list_wrap, target_canvas=self.cards_canvas, width=8, bg=BG_PAGE)
        self.cards_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 3), pady=4)

        return frame

    def _set_filter(self, label: str, refresh: bool = True) -> None:
        self._filter_var.set(label)
        for lbl, chip in self._filter_chips.items():
            if lbl == label:
                chip.config(bg=TXT_PRI, fg=TXT_INV, font=_f(8, True))
            else:
                chip.config(bg=BG_WELL, fg=TXT_SEC, font=_f(8, False))
        if refresh:
            self.refresh_notes_list()

    def _filter_note(self, note: Note) -> bool:
        f = self._filter_var.get()
        if f == "All":
            return True
        if f == "Queued":
            return note.status == NoteStatus.SYNCED
        if f == "Converted":
            return note.status == NoteStatus.CONVERTED
        if f == "Failed":
            return note.status == NoteStatus.FAILED
        return True

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self, root: tk.Tk) -> None:
        self._statusbar = tk.Frame(root, bg="#0F0F0F")
        if self.show_log:
            self._statusbar.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Label(self._statusbar, text="LOG", font=_fm(7),
                 bg="#0F0F0F", fg="#444444",
                 padx=12, pady=3).pack(side=tk.LEFT)

        Separator(self._statusbar, orient="v", color="#222222").pack(side=tk.LEFT, fill=tk.Y)

        self.log_text = tk.Text(
            self._statusbar, height=2,
            bg="#0F0F0F", fg="#7EC8A4",
            font=_fm(8), relief=tk.FLAT,
            padx=8, pady=4,
            insertbackground="#7EC8A4",
            selectbackground="#1E3A2F",
        )
        self.log_text.pack(fill=tk.X, expand=True)
        self.log_text.config(state=tk.DISABLED)

    def set_log_visible(self, visible: bool) -> None:
        """Toggle terminal activity log console visibility at the bottom of the window."""
        self.show_log = visible
        if hasattr(self, "_statusbar") and self._statusbar:
            if visible:
                self._statusbar.pack(fill=tk.X, side=tk.BOTTOM)
            else:
                self._statusbar.pack_forget()

    # ── Logging ───────────────────────────────────────────────────────────────

    def log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}]  {msg}\n"

        def _write():
            if hasattr(self, "log_text") and self.log_text:
                try:
                    self.log_text.config(state=tk.NORMAL)
                    self.log_text.insert(tk.END, line)
                    self.log_text.see(tk.END)
                    self.log_text.config(state=tk.DISABLED)
                except Exception:
                    pass

        self.call_on_ui(_write)

    # ── Notes list ────────────────────────────────────────────────────────────

    def refresh_notes_list(self) -> None:
        if not getattr(self, "scrollable_cards", None):
            return

        for w in self.scrollable_cards.winfo_children():
            w.destroy()

        all_notes = self.registry.all()
        notes = [n for n in all_notes if self._filter_note(n)]
        notes_sorted = sorted(
            notes,
            key=lambda n: n.synced_at or datetime.fromtimestamp(0, tz=timezone.utc),
            reverse=True,
        )

        # Update stats bar
        total = len(all_notes)
        converted = sum(1 for n in all_notes if n.status == NoteStatus.CONVERTED)
        if hasattr(self, "_stats_lbl"):
            self._stats_lbl.config(
                text=f"{total} notes  ·  {converted} converted  ·  {total-converted} pending")

        if not notes_sorted:
            es = tk.Frame(self.scrollable_cards, bg=BG_PAGE)
            es.pack(fill=tk.BOTH, expand=True, pady=60)

            if all_notes:
                # Notes exist but filtered out
                msg1 = "No notes match this filter."
                msg2 = "Try selecting a different category above."
            else:
                msg1 = "No notes found."
                msg2 = 'Wake the tablet, then click "Sync Now" to pull pages.'

            tk.Label(es, text=msg1, font=_f(12, True),
                     bg=BG_PAGE, fg=TXT_SEC).pack(pady=(0, 6))
            tk.Label(es, text=msg2, font=_f(9),
                     bg=BG_PAGE, fg=TXT_TER).pack()
            return

        for i, note in enumerate(notes_sorted):
            if i > 0:
                Separator(self.scrollable_cards, color=BORD_SUB).pack(
                    fill=tk.X, padx=16)
            card = NoteCard(
                self.scrollable_cards, note=note,
                on_retry=self.handle_retry_note,
                on_edit=self.handle_edit_note,
                on_convert_ocr=self.handle_convert_ocr,
                on_convert_ai=self.handle_convert_ai,
                on_view_md=self.handle_view_md,
            )
            card.pack(fill=tk.X, padx=16, pady=(8 if i == 0 else 6, 0))

    def handle_view_md(self, note: Note, md_path: str) -> None:
        """Open the transcribed Markdown modal viewer."""
        title = Path(md_path).stem.replace("_", " ").title()
        ModernMarkdownViewerDialog(
            parent=self.root,
            title=title,
            md_path=md_path,
        )


    # ── Sync ─────────────────────────────────────────────────────────────────

    def _set_sync_ui(self, syncing: bool) -> None:
        self._sync_active = syncing
        try:
            if syncing:
                self._btn_sync.config(text="Syncing...", fg=TXT_TER,
                                      cursor="arrow")
            else:
                self._btn_sync.config(text="Sync Now", fg=TXT_INV,
                                      cursor="hand2")
        except Exception:
            pass

    def handle_sync_now(self) -> None:
        if self._sync_active:
            return

        def _worker():
            self.call_on_ui(lambda: self._set_sync_ui(True))
            self.log("[Sync] Synchronizing offline notes from tablet memory...")
            mac     = "25:6C:BB:8D:19:50"
            out_dir = self.config.output_directory

            try:
                if self.bridge:
                    pages = self.bridge.sync_offline_pages(output_dir=out_dir, mac=mac, delete_after_export=False)
                else:
                    sync_mgr = OfflineSyncManager(mac=mac, output_dir=out_dir)
                    pages = asyncio.run(sync_mgr.run_sync(delete_after_export=False))

                if not pages:
                    self.log("[Sync] No offline pages found in tablet memory.")
                else:
                    self.log(f"[Sync] Successfully pulled {len(pages)} page(s).")

                self.registry.load_from_disk(out_dir)
                self.registry.load_from_disk("./exported_notes")
                self.call_on_ui(self.refresh_notes_list)
            except Exception as e:
                self.log(f"[Sync Notice] {e}")
            finally:
                self.call_on_ui(lambda: self._set_sync_ui(False))

        threading.Thread(target=_worker, daemon=True).start()

    # ── Retry / Clear ─────────────────────────────────────────────────────────

    def handle_retry_note(self, note: Note) -> None:
        if not self.pipeline or note.status != NoteStatus.FAILED:
            return
        self.log(f"[Retry] {Path(note.svg_path).stem}")
        try:
            self.pipeline.user_retries_note(user=object(), note=note)
            self.pipeline.begin_conversion(note)
            self.refresh_notes_list()
        except Exception as e:
            self.log(f"[Retry Error] {e}")

    def handle_clear_synced(self) -> None:
        if not self.pipeline:
            return
        self.log("[Clear] Removing synced pages from device memory...")
        self.pipeline.clear_synced_pages(user=object(), device=object())
        self.refresh_notes_list()
        self.log("[Clear] Done.")

    def handle_clear_all(self) -> None:
        if not self.pipeline:
            return
        if ModernModalDialog.confirm(
            parent=self.root,
            title="Clear All Pages from Device",
            message="Permanently delete all pages from tablet memory?\n\nUnsynced pages will be lost permanently.",
            confirm_text="Delete All",
            is_danger=True,
        ):
            self.log("[Clear] Wiping all device memory...")
            self.pipeline.clear_all_pages(user=object(), device=object())
            self.refresh_notes_list()
            self.log("[Clear] Device memory cleared.")

    # ── Note Editor Handlers ──────────────────────────────────────────────────

    def handle_edit_note(self, note: Note) -> None:
        """Open the full-page editor for a note."""
        self._editing_note = note
        if self._editor_frame:
            self._editor_frame.destroy()
            self._editor_frame = None

        self._editor_frame = NoteEditorPage(
            self._page_stack,
            note=note,
            on_save=self._on_editor_saved,
            on_back=lambda: self._show_page(self.PAGE_NOTES),
        )
        self._show_page(self.PAGE_EDITOR)
        self.log(f"[Editor] Opened {Path(note.svg_path).name} for annotation.")

    def _on_editor_saved(self, note: Note) -> None:
        """Handle save callback from the note editor."""
        self.log(f"[Editor] Saved annotations to {Path(note.svg_path).name}")
        note.status = NoteStatus.SYNCED
        self._show_page(self.PAGE_NOTES)
        self.refresh_notes_list()

    # ── HTR / Conversion Handlers ─────────────────────────────────────────────

    def _derive_title(self, note: Note, raw_text: str) -> str:
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if lines:
            candidate = re.sub(r"[^\w\s-]", "", lines[0]).strip().replace(" ", "_").lower()
            if candidate and len(candidate) <= 40:
                return candidate
        if note.filename and note.filename.title_part:
            return note.filename.title_part
        if note.svg_path:
            return Path(note.svg_path).stem.replace(" ", "_").lower()
        return "note"

    def _apply_conversion_result(self, note: Note, title: str, raw_text: str, md_content: str) -> None:
        is_cyclops = bool(re.search(r"\bcyclops\b", raw_text, re.IGNORECASE))
        category = NoteCategory.WORK if is_cyclops else NoteCategory.PERSONAL
        tags = ["engineering"] if category == NoteCategory.WORK else ["notes"]

        sync_date_str = (note.synced_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        fm = build_frontmatter(
            title=title.replace("_", " ").title(),
            sync_date=sync_date_str,
            category=category,
            tags=tags,
        )
        fm_block = render_frontmatter(fm)
        full_md = f"{fm_block}\n{md_content}\n\n![Note Sketch]({Path(note.svg_path).name})\n"

        result = ConversionResult(
            success=True,
            derived_title=title,
            category=category,
            markdown=full_md,
            tags=tags,
        )

        if self.pipeline:
            if note.status != NoteStatus.CONVERTING:
                note.status = NoteStatus.CONVERTING
            self.pipeline.conversion_succeeded(note, result)
        else:
            note.status = NoteStatus.CONVERTED
            note.category = category
            synced_at = note.synced_at or datetime.now(timezone.utc)
            date_str = synced_at.strftime("%d%m%Y")
            note.filename = NoteFilename(date_part=date_str, title_part=title)
            out_dir = Path(self.config.output_directory) / category.value
            out_dir.mkdir(parents=True, exist_ok=True)
            md_path = out_dir / note.filename.md_filename()
            md_path.write_text(full_md, encoding="utf-8")
            note.markdown_path = str(md_path)
            note.converted_at = datetime.now(timezone.utc)

    def handle_convert_ocr(self, note: Note) -> None:
        """Run local Tesseract HTR on the given note."""
        if not note.svg_path or not Path(note.svg_path).exists():
            self.log("[OCR Error] SVG file not found.")
            return

        def _worker():
            self.log(f"[OCR] Starting Tesseract HTR on {Path(note.svg_path).name}...")
            if self.pipeline:
                if note.status not in (NoteStatus.SYNCED, NoteStatus.CONVERTING):
                    note.status = NoteStatus.SYNCED
                    note.attempt_count = 0
                if not self.pipeline.begin_conversion(note):
                    note.status = NoteStatus.CONVERTING
                    note.attempt_count = 1
            else:
                note.status = NoteStatus.CONVERTING
            self.call_on_ui(self.refresh_notes_list)

            try:
                raw_text, md_content = htr_module.convert_tesseract(
                    note.svg_path,
                    title=Path(note.svg_path).stem.replace("_", " ").title(),
                )
                title = self._derive_title(note, raw_text)
                self._apply_conversion_result(note, title, raw_text, md_content)
                self.log(f"[OCR] Converted {Path(note.svg_path).name} -> Markdown ({title})")
            except Exception as e:
                self.log(f"[OCR Error] {e}")
                if self.pipeline:
                    if note.status != NoteStatus.CONVERTING:
                        note.status = NoteStatus.CONVERTING
                    self.pipeline.conversion_failed(note, ConversionResult(success=False, error=str(e)))
                else:
                    note.status = NoteStatus.FAILED
            finally:
                self.call_on_ui(self.refresh_notes_list)

        threading.Thread(target=_worker, daemon=True).start()

    def handle_convert_ai(self, note: Note) -> None:
        """Run Gemini Vision AI HTR on the given note."""
        if not note.svg_path or not Path(note.svg_path).exists():
            self.log("[AI Convert Error] SVG file not found.")
            return

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            api_key = ModernModalDialog.prompt(
                parent=self.root,
                title="Gemini Vision API Key",
                message="Enter your Gemini API key to transcribe handwritten notes using Google Vision AI:",
                confirm_text="Save & Transcribe",
            )
            if not api_key:
                self.log("[AI Convert] Cancelled: no GEMINI_API_KEY provided.")
                return
            os.environ["GEMINI_API_KEY"] = api_key

        def _worker():
            self.log(f"[AI Convert] Sending {Path(note.svg_path).name} to Gemini Vision...")
            if self.pipeline:
                if note.status not in (NoteStatus.SYNCED, NoteStatus.CONVERTING):
                    note.status = NoteStatus.SYNCED
                    note.attempt_count = 0
                if not self.pipeline.begin_conversion(note):
                    note.status = NoteStatus.CONVERTING
                    note.attempt_count = 1
            else:
                note.status = NoteStatus.CONVERTING
            self.call_on_ui(self.refresh_notes_list)

            try:
                raw_text, md_content = htr_module.convert_gemini(
                    note.svg_path,
                    title=Path(note.svg_path).stem.replace("_", " ").title(),
                    api_key=api_key,
                )
                title = self._derive_title(note, raw_text)
                self._apply_conversion_result(note, title, raw_text, md_content)
                self.log(f"[AI Convert] Converted {Path(note.svg_path).name} with Gemini -> Markdown ({title})")
            except Exception as e:
                self.log(f"[AI Convert Error] {e}")
                if self.pipeline:
                    if note.status != NoteStatus.CONVERTING:
                        note.status = NoteStatus.CONVERTING
                    self.pipeline.conversion_failed(note, ConversionResult(success=False, error=str(e)))
                else:
                    note.status = NoteStatus.FAILED
            finally:
                self.call_on_ui(self.refresh_notes_list)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_close(self) -> None:
        """Cleanly shutdown hardware streams, system tray, and close window."""
        if hasattr(self, "_tray") and self._tray:
            try:
                self._tray.stop()
            except Exception:
                pass
        if self.bridge:
            try:
                self.bridge.stop_pen_input()
            except Exception:
                pass
        if self.root:
            self.root.destroy()

    def run(self) -> None:
        root = self.build_window()
        root.mainloop()


if __name__ == "__main__":
    app = HuionNotePipelineApp()
    app.run()
