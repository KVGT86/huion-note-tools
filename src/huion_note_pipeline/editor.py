from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING
import tkinter as tk

if TYPE_CHECKING:
    from huion_note_pipeline.models import Note

# ---------------------------------------------------------------------------
# Colour palette (light mode, no emojis)
# ---------------------------------------------------------------------------
BG_MAIN   = '#FFFFFF'
BG_PAGE   = '#F7F6F3'
BG_CANVAS = '#FDFCFA'
BG_WELL   = '#EFEFEE'
BORD_SUB  = '#E3E2DE'
TXT_PRI   = '#37352F'
TXT_SEC   = '#787774'
TXT_INV   = '#FFFFFF'


class NoteEditorPage(tk.Frame):
    """Tkinter page for viewing and annotating a Huion note SVG."""

    def __init__(
        self,
        master: tk.Misc,
        note: "Note",
        on_save,
        on_back,
    ) -> None:
        super().__init__(master, bg=BG_MAIN)
        self._note = note
        self._on_save = on_save
        self._on_back = on_back

        # Annotation state
        self._annotation_strokes: list[list[tuple[float, float]]] = []
        self._current_stroke: list[tuple[float, float]] = []

        # Transform state (set in _redraw_base)
        self._scale: float = 1.0
        self._offset_x: float = 0.0
        self._offset_y: float = 0.0

        # SVG dimensions (set in _load_svg)
        self._svg_width: float = 900.0
        self._svg_height: float = 1190.0

        self._load_svg()
        self._build_ui()

    # ------------------------------------------------------------------
    # SVG parsing
    # ------------------------------------------------------------------

    def _load_svg(self) -> None:
        """Parse the note's SVG file and extract stroke paths."""
        self._svg_strokes: list[list[tuple[float, float]]] = []

        svg_path = Path(self._note.svg_path)
        if not svg_path.exists():
            return

        try:
            tree = ET.parse(svg_path)
        except ET.ParseError:
            return

        root = tree.getroot()

        # Extract width / height from root element
        raw_w = root.get('width', str(self._svg_width))
        raw_h = root.get('height', str(self._svg_height))
        try:
            self._svg_width = float(re.sub(r'[^0-9.]', '', raw_w) or self._svg_width)
        except ValueError:
            pass
        try:
            self._svg_height = float(re.sub(r'[^0-9.]', '', raw_h) or self._svg_height)
        except ValueError:
            pass

        # Walk all elements, collect path 'd' attributes
        for elem in root.iter():
            tag = elem.tag
            # Strip XML namespace if present
            if '}' in tag:
                tag = tag.split('}', 1)[1]
            if tag.lower() == 'path':
                d = elem.get('d', '')
                if not d:
                    continue
                coords = re.findall(r'([0-9]+(?:\.[0-9]*)?),([0-9]+(?:\.[0-9]*)?)', d)
                points = [(float(x), float(y)) for x, y in coords]
                if points:
                    self._svg_strokes.append(points)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Build the toolbar, canvas, and hint bar."""
        self.pack(fill=tk.BOTH, expand=True)

        # ---- Toolbar ---------------------------------------------------
        toolbar = tk.Frame(self, bg=BG_PAGE, pady=8)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        left_bar = tk.Frame(toolbar, bg=BG_PAGE)
        left_bar.pack(side=tk.LEFT, padx=12)

        self._back_btn = self._make_button(
            left_bar, '←  Back', self._on_back, padx=10
        )
        self._back_btn.pack(side=tk.LEFT, padx=(0, 12))

        title_text = "Untitled"
        if getattr(self._note, "filename", None) and self._note.filename.title_part:
            title_text = self._note.filename.title_part.replace("_", " ").title()
        elif getattr(self._note, "svg_path", None):
            title_text = Path(self._note.svg_path).stem.replace("_", " ").title()

        tk.Label(
            left_bar,
            text=title_text,
            bg=BG_PAGE,
            fg=TXT_PRI,
            font=('Helvetica', 12, 'bold'),
        ).pack(side=tk.LEFT)

        right_bar = tk.Frame(toolbar, bg=BG_PAGE)
        right_bar.pack(side=tk.RIGHT, padx=12)

        self._undo_btn = self._make_button(right_bar, 'Undo', self._undo, padx=10)
        self._undo_btn.pack(side=tk.LEFT, padx=4)

        self._clear_btn = self._make_button(
            right_bar, 'Clear Annotations', self._clear_annotations, padx=10
        )
        self._clear_btn.pack(side=tk.LEFT, padx=4)

        self._save_btn = self._make_button(
            right_bar, 'Save', self._save, padx=14, accent=True
        )
        self._save_btn.pack(side=tk.LEFT, padx=(4, 0))

        # Separator
        sep = tk.Frame(self, bg=BORD_SUB, height=1)
        sep.pack(fill=tk.X)

        # ---- Canvas well -----------------------------------------------
        well = tk.Frame(self, bg=BG_WELL, padx=16, pady=16)
        well.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(
            well,
            bg=BG_CANVAS,
            highlightthickness=0,
            cursor='crosshair',
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Bind events
        self._canvas.bind('<Configure>', self._on_configure)
        self._canvas.bind('<B1-Motion>', self._on_drag)
        self._canvas.bind('<ButtonRelease-1>', self._on_release)

        # ---- Hint bar --------------------------------------------------
        hint = tk.Frame(self, bg=BG_PAGE, pady=6)
        hint.pack(side=tk.BOTTOM, fill=tk.X)

        tk.Label(
            hint,
            text='Draw to annotate. Existing strokes shown in grey.',
            bg=BG_PAGE,
            fg=TXT_SEC,
            font=('Helvetica', 11),
        ).pack(padx=12)

    # ------------------------------------------------------------------
    # Button factory
    # ------------------------------------------------------------------

    def _make_button(
        self,
        parent: tk.Misc,
        text: str,
        command,
        padx: int = 8,
        accent: bool = False,
    ) -> tk.Label:
        bg_normal = TXT_PRI if accent else BG_WELL
        fg_normal = TXT_INV if accent else TXT_PRI
        bg_hover  = '#1C1C1C' if accent else BORD_SUB

        lbl = tk.Label(
            parent,
            text=text,
            bg=bg_normal,
            fg=fg_normal,
            font=('Helvetica', 11),
            padx=padx,
            pady=4,
            cursor='hand2',
        )
        lbl.bind('<Button-1>', lambda _e: command())
        lbl.bind('<Enter>',    lambda _e: lbl.configure(bg=bg_hover))
        lbl.bind('<Leave>',    lambda _e: lbl.configure(bg=bg_normal))
        return lbl

    # ------------------------------------------------------------------
    # Canvas event handlers & Pen Stream Routing
    # ------------------------------------------------------------------

    def _on_configure(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        self._redraw_base()
        self._redraw_annotations()

    def on_pen_point(self, point: Any) -> None:
        """Handle hardware pen stream points from the tablet in real-time."""
        if point.touch or point.pressure > 0:
            # Map tablet hardware coordinates (0..28200, 0..37400) into SVG space
            svg_x = (point.x / 28200.0) * self._svg_width
            svg_y = (point.y / 37400.0) * self._svg_height
            cx, cy = self._to_canvas(svg_x, svg_y)

            self._current_stroke.append((cx, cy))
            n = len(self._current_stroke)
            if n < 2:
                return

            p0, p1 = self._current_stroke[-2], self._current_stroke[-1]
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            if (dx * dx + dy * dy) < 0.2 and n > 2:
                return

            if n == 2:
                coords = [p0[0], p0[1], p1[0], p1[1]]
            else:
                pp = self._current_stroke[-3]
                mx0 = (pp[0] + p0[0]) / 2.0
                my0 = (pp[1] + p0[1]) / 2.0
                mx1 = (p0[0] + p1[0]) / 2.0
                my1 = (p0[1] + p1[1]) / 2.0
                coords = [mx0, my0, p0[0], p0[1], mx1, my1]

            self._canvas.create_line(
                *coords,
                fill='#1C1C1C',
                width=1.8,
                smooth=True,
                splinesteps=36,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
                tags='annotation',
            )
        else:
            if self._current_stroke:
                self._annotation_strokes.append(list(self._current_stroke))
                self._current_stroke = []

    def _on_drag(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        x, y = float(event.x), float(event.y)
        if self._current_stroke:
            prev_x, prev_y = self._current_stroke[-1]
            self._canvas.create_line(
                prev_x, prev_y, x, y,
                fill='#1C1C1C',
                width=1.8,
                smooth=True,
                splinesteps=36,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
                tags='annotation',
            )
        self._current_stroke.append((x, y))

    def _on_release(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._current_stroke:
            self._annotation_strokes.append(list(self._current_stroke))
            self._current_stroke = []

    # ------------------------------------------------------------------
    # Coordinate transforms
    # ------------------------------------------------------------------

    def _to_canvas(self, x: float, y: float) -> tuple[float, float]:
        """Convert SVG coordinates to canvas coordinates."""
        return (
            x * self._scale + self._offset_x,
            y * self._scale + self._offset_y,
        )

    def _to_svg(self, cx: float, cy: float) -> tuple[float, float]:
        """Convert canvas coordinates to SVG coordinates."""
        return (
            (cx - self._offset_x) / self._scale,
            (cy - self._offset_y) / self._scale,
        )

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _compute_transform(self) -> None:
        """Recompute scale and offsets to fit A5 SVG inside canvas with padding."""
        padding = 24
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()

        available_w = max(cw - 2 * padding, 1)
        available_h = max(ch - 2 * padding, 1)

        scale_x = available_w / self._svg_width if self._svg_width else 1.0
        scale_y = available_h / self._svg_height if self._svg_height else 1.0
        self._scale = min(scale_x, scale_y)

        # Centre the scaled SVG
        scaled_w = self._svg_width * self._scale
        scaled_h = self._svg_height * self._scale
        self._offset_x = (cw - scaled_w) / 2.0
        self._offset_y = (ch - scaled_h) / 2.0

    def _redraw_base(self) -> None:
        """Clear canvas, recompute transform, draw A5 sheet backing, and draw SVG strokes in grey."""
        self._canvas.delete('all')
        self._compute_transform()

        scaled_w = self._svg_width * self._scale
        scaled_h = self._svg_height * self._scale

        # Draw A5 paper background with subtle 1px border
        self._canvas.create_rectangle(
            self._offset_x, self._offset_y,
            self._offset_x + scaled_w, self._offset_y + scaled_h,
            fill='#FFFFFF', outline='#E3E2DE', width=1,
            tags='paper'
        )

        for stroke in self._svg_strokes:
            if len(stroke) < 2:
                continue
            flat: list[float] = []
            for sx, sy in stroke:
                cx, cy = self._to_canvas(sx, sy)
                flat.extend([cx, cy])
            self._canvas.create_line(
                *flat,
                fill='#C0BFBC',
                width=1.2,
                smooth=True,
                splinesteps=36,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
                tags='base',
            )

    def _redraw_annotations(self) -> None:
        """Redraw all saved annotation strokes on top of the base."""
        self._canvas.delete('annotation')
        for stroke in self._annotation_strokes:
            if len(stroke) < 2:
                continue
            flat: list[float] = []
            for cx, cy in stroke:
                flat.extend([cx, cy])
            self._canvas.create_line(
                *flat,
                fill='#1C1C1C',
                width=1.8,
                smooth=True,
                splinesteps=36,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
                tags='annotation',
            )

    def _redraw_all(self) -> None:
        """Full redraw: base SVG then all annotation strokes."""
        self._redraw_base()
        self._redraw_annotations()

    # ------------------------------------------------------------------
    # Toolbar actions
    # ------------------------------------------------------------------

    def _undo(self) -> None:
        """Remove the last annotation stroke and redraw."""
        if self._annotation_strokes:
            self._annotation_strokes.pop()
        self._redraw_all()

    def _clear_annotations(self) -> None:
        """Remove all annotation strokes and redraw."""
        self._annotation_strokes.clear()
        self._redraw_all()

    def _save(self) -> None:
        """Write annotation strokes back into the SVG file and call on_save."""
        svg_path = Path(self._note.svg_path)
        if not svg_path.exists():
            self._on_save(self._note)
            return

        original_text = svg_path.read_text(encoding='utf-8')

        # Build new <path> elements for each annotation stroke
        new_paths: list[str] = []
        for stroke in self._annotation_strokes:
            if len(stroke) < 2:
                continue
            # Convert canvas coords back to SVG coordinate space
            svg_points = [self._to_svg(cx, cy) for cx, cy in stroke]
            start_x, start_y = svg_points[0]
            d_parts = [f'M {start_x:.3f},{start_y:.3f}']
            for sx, sy in svg_points[1:]:
                d_parts.append(f'L {sx:.3f},{sy:.3f}')
            d_str = ' '.join(d_parts)
            new_paths.append(
                f'<path d="{d_str}" '
                f'stroke="#1C1C1C" stroke-width="2" fill="none" '
                f'stroke-linecap="round" stroke-linejoin="round"/>'
            )

        if new_paths:
            insertion = '\n'.join(new_paths) + '\n'
            modified = original_text.replace('</svg>', insertion + '</svg>', 1)
        else:
            modified = original_text

        svg_path.write_text(modified, encoding='utf-8')
        self._on_save(self._note)
