import asyncio
import datetime
import logging
import math
import os
import sys
import threading
import tkinter as tk
from typing import List, Optional, Tuple

from .models import PenPoint, Stroke, PenType
from .renderer import MultiFormatRenderer

log = logging.getLogger("huion.live")

class LiveViewerWindow:
    """Refined Live Visualizer with smooth quadratic Bezier spline inking and realistic pen dynamics."""

    PAGE_WIDTH = 28200
    PAGE_HEIGHT = 37400

    def __init__(self, output_dir: str, on_close_callback=None):
        self.output_dir = output_dir
        self.on_close_callback = on_close_callback
        self.renderer = MultiFormatRenderer()

        self.root = tk.Tk()
        self.root.title("Huion Note X10 — Live Inking Canvas")
        self.root.geometry("640x880")
        self.root.configure(bg="#212121")

        # State
        self.session_date = datetime.date.today().isoformat()
        self.page_number = 1
        self.strokes: List[Stroke] = []
        self.current_points: List[PenPoint] = []
        self.is_running = True

        # Header status bar
        self.header_frame = tk.Frame(self.root, bg="#2a2a2a", pady=8, padx=12)
        self.header_frame.pack(fill=tk.X, side=tk.TOP)

        self.status_label = tk.Label(
            self.header_frame,
            text=f"Page {self.page_number}  |  0 Strokes  |  [N] Next Page   [S] Save   [C] Clear   [Q] Quit",
            bg="#2a2a2a", fg="#e0e0e0", font=("DejaVu Sans", 10, "bold")
        )
        self.status_label.pack(side=tk.LEFT)

        self.btn_next = tk.Button(
            self.header_frame, text="Next Page (+)", bg="#3b82f6", fg="#ffffff",
            font=("DejaVu Sans", 9, "bold"), relief=tk.FLAT, padx=10, pady=2,
            command=self.next_page
        )
        self.btn_next.pack(side=tk.RIGHT, padx=4)

        self.btn_save = tk.Button(
            self.header_frame, text="Save Page", bg="#10b981", fg="#ffffff",
            font=("DejaVu Sans", 9, "bold"), relief=tk.FLAT, padx=8, pady=2,
            command=self.save_current_page
        )
        self.btn_save.pack(side=tk.RIGHT, padx=4)

        # Drawing canvas with clean paper background
        self.canvas_frame = tk.Frame(self.root, bg="#212121", padx=12, pady=12)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            self.canvas_frame,
            bg="#faf9f6",  # warm off-white paper color
            highlightthickness=1,
            highlightbackground="#404040"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Key Bindings
        self.root.bind("<Key-n>", lambda e: self.next_page())
        self.root.bind("<Key-N>", lambda e: self.next_page())
        self.root.bind("<Key-s>", lambda e: self.save_current_page())
        self.root.bind("<Key-S>", lambda e: self.save_current_page())
        self.root.bind("<Key-c>", lambda e: self.clear_canvas())
        self.root.bind("<Key-C>", lambda e: self.clear_canvas())
        self.root.bind("<Key-q>", lambda e: self.close())
        self.root.bind("<Key-Q>", lambda e: self.close())
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def add_point(self, pt: PenPoint, pen_down: bool):
        """Dispatched from BLE thread into Tk mainloop."""
        self.root.after(0, self._process_point, pt, pen_down)

    def _get_canvas_coords(self, pt: PenPoint) -> Tuple[float, float]:
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        sx = (pt.x / float(self.PAGE_WIDTH)) * cw
        sy = (pt.y / float(self.PAGE_HEIGHT)) * ch
        return sx, sy

    def _calculate_pen_width(self, pressure: int) -> float:
        """Calculates natural, elegant stroke width based on pressure (1.0px to 2.8px)."""
        norm_p = min(1.0, max(0.0, pressure / 8192.0))
        # Non-linear dynamic curve for realistic pen-on-paper inking
        return max(1.0, 0.9 + (norm_p ** 1.2) * 1.9)

    def _process_point(self, pt: PenPoint, pen_down: bool):
        if not self.is_running:
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw <= 1 or ch <= 1:
            return

        if pen_down and pt.pressure > 0:
            self.current_points.append(pt)
            n = len(self.current_points)

            if n >= 2:
                p0 = self.current_points[-2]
                p1 = self.current_points[-1]

                x0, y0 = self._get_canvas_coords(p0)
                x1, y1 = self._get_canvas_coords(p1)

                # Distance threshold filtering to prevent micro-jitter
                dist = math.hypot(x1 - x0, y1 - y0)
                if dist < 0.5 and n > 2:
                    return

                width = self._calculate_pen_width(p1.pressure)

                if n == 2:
                    # Initial stroke start line
                    self.canvas.create_line(
                        x0, y0, x1, y1,
                        fill="#1a1a1a",
                        width=width,
                        capstyle=tk.ROUND,
                        joinstyle=tk.ROUND,
                        smooth=True
                    )
                else:
                    # Smooth midpoint quadratic Bezier segment
                    p_prev = self.current_points[-3]
                    xp, yp = self._get_canvas_coords(p_prev)

                    mid_prev_x = (xp + x0) / 2.0
                    mid_prev_y = (yp + y0) / 2.0
                    mid_curr_x = (x0 + x1) / 2.0
                    mid_curr_y = (y0 + y1) / 2.0

                    self.canvas.create_line(
                        mid_prev_x, mid_prev_y,
                        x0, y0,
                        mid_curr_x, mid_curr_y,
                        fill="#1a1a1a",
                        width=width,
                        capstyle=tk.ROUND,
                        joinstyle=tk.ROUND,
                        smooth=True,
                        splinesteps=12
                    )
        else:
            if len(self.current_points) > 1:
                self.strokes.append(Stroke(points=list(self.current_points), pen_type=PenType.BALLPOINT))
                self._update_status()
            self.current_points.clear()

    def handle_hardware_button(self):
        """Hardware button pressed on notebook -> Auto save and turn to new page."""
        self.root.after(0, self.next_page)

    def next_page(self):
        if self.strokes:
            self.save_current_page()
        self.page_number += 1
        self.strokes.clear()
        self.current_points.clear()
        self.canvas.delete("all")
        self._update_status()
        log.info(f"Turned to new blank page: {self.page_number}")

    def clear_canvas(self):
        self.strokes.clear()
        self.current_points.clear()
        self.canvas.delete("all")
        self._update_status()

    def save_current_page(self):
        if not self.strokes:
            return
        folder = os.path.join(self.output_dir, self.session_date, "live_session")
        base_name = f"{self.session_date}_page_{self.page_number:02d}"
        artifacts = self.renderer.export_all(self.strokes, folder, base_name)
        log.info(f"Live page saved to {artifacts.folder_path}/{artifacts.svg_filename}")
        self.status_label.config(text=f"Saved Page {self.page_number} -> {artifacts.svg_filename}")

    def _update_status(self):
        self.status_label.config(
            text=f"Page {self.page_number}  |  {len(self.strokes)} Strokes  |  [N] Next Page   [S] Save   [C] Clear   [Q] Quit"
        )

    def close(self):
        if self.strokes:
            self.save_current_page()
        self.is_running = False
        if self.on_close_callback:
            self.on_close_callback()
        self.root.destroy()

    def start_loop(self):
        self.root.mainloop()
