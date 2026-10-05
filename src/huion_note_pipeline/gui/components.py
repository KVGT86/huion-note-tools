"""Modern Notion / Apple style UI components for Tkinter.

Provides:
  - ModernScrollbar: Slim, rounded, interactive overlay scrollbar.
  - ModernModalDialog: Sleek modal popup for alerts, confirmations, and text inputs.
  - ModernDropdownMenu: Notion-style popup action menu.
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional, Callable, List, Tuple, Any


# ── Theme Palette ─────────────────────────────────────────────────────────────
BG_PAGE     = "#F7F6F3"
BG_CARD     = "#FFFFFF"
BG_HOVER    = "#F1F1EF"
BG_ACTIVE   = "#EBEBEA"
BG_WELL     = "#EEEDE9"
BORD_SUB    = "#D8D7D3"
BORD_MED    = "#B8B7B3"
BORD_FOCUS  = "#1F1E1A"

TXT_PRI     = "#1F1E1A"
TXT_SEC     = "#6B6A67"
TXT_TER     = "#A8A6A3"
TXT_INV     = "#FFFFFF"

ACCENT_DANGER = "#E53935"
ACCENT_DANGER_HOVER = "#C62828"


def _font(size: int, bold: bool = False) -> tuple:
    return ("sans-serif", size, "bold") if bold else ("sans-serif", size)


# ── Modern Slim Scrollbar ─────────────────────────────────────────────────────

class ModernScrollbar(tk.Canvas):
    """Ultra-slim, rounded Notion-style scrollbar for Canvas widgets."""

    def __init__(
        self,
        master: tk.Widget,
        target_canvas: tk.Canvas,
        width: int = 8,
        bg: str = BG_PAGE,
        thumb_color: str = "#D3D1CB",
        thumb_hover: str = "#A09E98",
        **kw,
    ) -> None:
        super().__init__(master, width=width, bg=bg, highlightthickness=0, bd=0, **kw)
        self.target = target_canvas
        self.bar_width = width
        self.thumb_color = thumb_color
        self.thumb_hover = thumb_hover
        self._current_color = thumb_color

        self._top_frac = 0.0
        self._bot_frac = 1.0
        self._drag_start_y = 0
        self._drag_start_top = 0.0
        self._is_dragging = False

        # Link with target canvas
        self.target.configure(yscrollcommand=self.set_scroll)

        # Event bindings
        self.bind("<Configure>", lambda _: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

        # Cross-platform mousewheel bindings on target canvas
        self._bind_mousewheel(self.target)

    def set_scroll(self, top: float | str, bot: float | str) -> None:
        self._top_frac = float(top)
        self._bot_frac = float(bot)
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        h = self.winfo_height()
        if h <= 10 or (self._bot_frac - self._top_frac) >= 0.999:
            return  # No scrollbar needed if content fits

        y0 = max(2, int(self._top_frac * h))
        y1 = min(h - 2, int(self._bot_frac * h))
        min_thumb_h = 24
        if y1 - y0 < min_thumb_h:
            y1 = min(h - 2, y0 + min_thumb_h)

        w = self.bar_width
        r = (w - 2) / 2.0
        # Draw smooth rounded pill thumb
        self.create_oval(1, y0, w - 1, y0 + r * 2, fill=self._current_color, outline="", tags="thumb")
        self.create_rectangle(1, y0 + r, w - 1, y1 - r, fill=self._current_color, outline="", tags="thumb")
        self.create_oval(1, y1 - r * 2, w - 1, y1, fill=self._current_color, outline="", tags="thumb")

    def _on_enter(self, _=None) -> None:
        self._current_color = self.thumb_hover
        self._redraw()

    def _on_leave(self, _=None) -> None:
        if not self._is_dragging:
            self._current_color = self.thumb_color
            self._redraw()

    def _on_click(self, event: tk.Event) -> None:
        h = self.winfo_height()
        if h <= 0:
            return
        y0 = int(self._top_frac * h)
        y1 = int(self._bot_frac * h)

        if y0 <= event.y <= y1:
            self._is_dragging = True
            self._drag_start_y = event.y
            self._drag_start_top = self._top_frac
        else:
            # Jump scroll towards clicked position
            frac = event.y / float(h)
            span = self._bot_frac - self._top_frac
            new_top = max(0.0, min(1.0 - span, frac - span / 2.0))
            self.target.yview_moveto(new_top)

    def _on_drag(self, event: tk.Event) -> None:
        if not self._is_dragging:
            return
        h = self.winfo_height()
        if h <= 0:
            return
        dy = event.y - self._drag_start_y
        d_frac = dy / float(h)
        span = self._bot_frac - self._top_frac
        new_top = max(0.0, min(1.0 - span, self._drag_start_top + d_frac))
        self.target.yview_moveto(new_top)

    def _on_release(self, _=None) -> None:
        self._is_dragging = False
        self._current_color = self.thumb_color
        self._redraw()

    def _bind_mousewheel(self, widget: tk.Widget) -> None:
        def _on_scroll(event: tk.Event) -> str:
            # Linux scroll wheel
            if event.num == 4:
                self.target.yview_scroll(-3, "units")
            elif event.num == 5:
                self.target.yview_scroll(3, "units")
            # Windows / macOS
            elif hasattr(event, "delta") and event.delta != 0:
                self.target.yview_scroll(int(-1 * (event.delta / 120) * 3), "units")
            return "break"

        widget.bind_all("<Button-4>", _on_scroll)
        widget.bind_all("<Button-5>", _on_scroll)
        widget.bind_all("<MouseWheel>", _on_scroll)


# ── Modern Modal Dialogs ──────────────────────────────────────────────────────

class ModernModalDialog(tk.Toplevel):
    """Clean, card-based modal popup with Apple / Notion styling."""

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        title: str,
        message: str,
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel",
        is_danger: bool = False,
        prompt_input: bool = False,
        default_value: str = "",
        placeholder: str = "",
        width: int = 420,
    ) -> None:
        super().__init__(parent)
        self.result: Optional[Any] = None
        self.prompt_input = prompt_input

        self.overrideredirect(True)  # Borderless custom floating card
        self.configure(bg=BORD_MED)
        self.resizable(False, False)

        # Outer 1px border wrapper
        container = tk.Frame(self, bg=BG_CARD, padx=24, pady=22)
        container.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Title
        tk.Label(
            container, text=title,
            font=_font(11, True), bg=BG_CARD, fg=TXT_PRI,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 6))

        # Description Message
        tk.Label(
            container, text=message,
            font=_font(9), bg=BG_CARD, fg=TXT_SEC,
            justify=tk.LEFT, wraplength=width - 50, anchor="w",
        ).pack(fill=tk.X, pady=(0, 16))

        # Text input (for prompts / API keys)
        self.entry_var = tk.StringVar(value=default_value)
        if prompt_input:
            input_frame = tk.Frame(container, bg=BORD_MED, padx=1, pady=1)
            input_frame.pack(fill=tk.X, pady=(0, 18))
            self.entry = tk.Entry(
                input_frame, textvariable=self.entry_var,
                font=_font(9), bg=BG_CARD, fg=TXT_PRI,
                relief=tk.FLAT, bd=0, insertbackground=TXT_PRI,
            )
            self.entry.pack(fill=tk.X, padx=8, pady=6)
            self.entry.focus_set()

            # Focus ring effect
            self.entry.bind("<FocusIn>", lambda _: input_frame.configure(bg=BORD_FOCUS))
            self.entry.bind("<FocusOut>", lambda _: input_frame.configure(bg=BORD_MED))

        # Button action row (Cancel on left, Confirm on right)
        btn_row = tk.Frame(container, bg=BG_CARD)
        btn_row.pack(fill=tk.X, side=tk.BOTTOM, pady=(8, 0))

        # Cancel Button
        btn_cancel = tk.Label(
            btn_row, text=cancel_text,
            font=_font(9), bg=BG_WELL, fg=TXT_PRI,
            padx=14, pady=6, cursor="hand2",
        )
        btn_cancel.pack(side=tk.RIGHT, padx=(8, 0))
        btn_cancel.bind("<Enter>", lambda _: btn_cancel.configure(bg=BG_ACTIVE))
        btn_cancel.bind("<Leave>", lambda _: btn_cancel.configure(bg=BG_WELL))
        btn_cancel.bind("<Button-1>", lambda _: self._cancel())

        # Confirm Button
        confirm_bg = ACCENT_DANGER if is_danger else TXT_PRI
        confirm_hov = ACCENT_DANGER_HOVER if is_danger else "#1A1A1A"
        btn_confirm = tk.Label(
            btn_row, text=confirm_text,
            font=_font(9, True), bg=confirm_bg, fg=TXT_INV,
            padx=16, pady=6, cursor="hand2",
        )
        btn_confirm.pack(side=tk.RIGHT)
        btn_confirm.bind("<Enter>", lambda _: btn_confirm.configure(bg=confirm_hov))
        btn_confirm.bind("<Leave>", lambda _: btn_confirm.configure(bg=confirm_bg))
        btn_confirm.bind("<Button-1>", lambda _: self._confirm())

        # Keybindings
        self.bind("<Return>", lambda _: self._confirm())
        self.bind("<Escape>", lambda _: self._cancel())

        # Center on parent window
        self._center_on_parent(parent, width)

        # Make modal
        self.transient(parent)
        self.grab_set()
        parent.wait_window(self)

    def _center_on_parent(self, parent: tk.Widget, width: int) -> None:
        self.update_idletasks()
        pw = parent.winfo_width() or 800
        ph = parent.winfo_height() or 600
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        h = self.winfo_reqheight() or 180

        x = px + (pw - width) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{width}x{h}+{max(0, x)}+{max(0, y)}")

    def _confirm(self) -> None:
        if self.prompt_input:
            self.result = self.entry_var.get().strip()
        else:
            self.result = True
        self.destroy()

    def _cancel(self) -> None:
        self.result = None if self.prompt_input else False
        self.destroy()

    @classmethod
    def confirm(
        cls,
        parent: tk.Widget,
        title: str,
        message: str,
        confirm_text: str = "Confirm",
        is_danger: bool = False,
    ) -> bool:
        """Show modern confirmation dialog. Returns True if confirmed."""
        dialog = cls(
            parent=parent.winfo_toplevel(),
            title=title,
            message=message,
            confirm_text=confirm_text,
            is_danger=is_danger,
            prompt_input=False,
        )
        return bool(dialog.result)

    @classmethod
    def prompt(
        cls,
        parent: tk.Widget,
        title: str,
        message: str,
        confirm_text: str = "Submit",
        default_value: str = "",
    ) -> Optional[str]:
        """Show modern text input dialog. Returns string if submitted, None if cancelled."""
        dialog = cls(
            parent=parent.winfo_toplevel(),
            title=title,
            message=message,
            confirm_text=confirm_text,
            prompt_input=True,
            default_value=default_value,
        )
        return dialog.result


# ── Modern Dropdown Menu ──────────────────────────────────────────────────────

class ModernDropdownMenu:
    """Floating Notion-style dropdown menu attached to a trigger button."""

    def __init__(self, parent: tk.Widget) -> None:
        self.parent = parent
        self.menu_win: Optional[tk.Toplevel] = None
        self.items: List[Tuple[str, Callable[[], None], bool]] = []  # (label, cmd, is_danger)

    def add_option(self, label: str, command: Callable[[], None], is_danger: bool = False) -> None:
        self.items.append((label, command, is_danger))

    def show(self, trigger_widget: tk.Widget) -> None:
        if self.menu_win:
            self.hide()
            return

        top = tk.Toplevel(self.parent)
        top.overrideredirect(True)
        top.configure(bg=BORD_MED)
        self.menu_win = top

        card = tk.Frame(top, bg=BG_CARD, padx=4, pady=4)
        card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        for label, cmd, is_danger in self.items:
            fg_color = ACCENT_DANGER if is_danger else TXT_PRI
            item_lbl = tk.Label(
                card, text=label,
                font=_font(9), bg=BG_CARD, fg=fg_color,
                padx=12, pady=6, anchor="w", cursor="hand2",
            )
            item_lbl.pack(fill=tk.X)

            def _make_hover(lbl, danger):
                hov_bg = "#FFEBEE" if danger else BG_HOVER
                lbl.bind("<Enter>", lambda _: lbl.configure(bg=hov_bg))
                lbl.bind("<Leave>", lambda _: lbl.configure(bg=BG_CARD))

            _make_hover(item_lbl, is_danger)

            def _make_click(c):
                return lambda _: (self.hide(), c())

            item_lbl.bind("<Button-1>", _make_click(cmd))

        # Position below trigger widget
        top.update_idletasks()
        tx = trigger_widget.winfo_rootx()
        ty = trigger_widget.winfo_rooty() + trigger_widget.winfo_height() + 4
        tw = max(180, top.winfo_reqwidth())
        top.geometry(f"{tw}x{top.winfo_reqheight()}+{tx}+{ty}")

        # Dismiss when clicking anywhere outside
        top.bind("<FocusOut>", lambda _: self.hide())
        top.focus_set()

    def hide(self) -> None:
        if self.menu_win:
            try:
                self.menu_win.destroy()
            except Exception:
                pass
            self.menu_win = None


# ── Modern Settings Dialog ───────────────────────────────────────────────────

class ModernSettingsDialog(tk.Toplevel):
    """Notion / Apple style Settings modal window."""

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        mac_address: str,
        is_connected: Optional[bool],
        battery: Optional[int],
        total_notes_count: int,
        show_log: bool,
        on_retry_connect: Callable[[str], None],
        on_rescan_library: Callable[[], None],
        on_save_gemini_key: Callable[[str], None],
        on_toggle_log: Optional[Callable[[bool], None]] = None,
        width: int = 560,
    ) -> None:
        super().__init__(parent)
        self.on_retry_connect = on_retry_connect
        self.on_rescan_library = on_rescan_library
        self.on_save_gemini_key = on_save_gemini_key
        self.on_toggle_log = on_toggle_log
        self.mac_address = mac_address

        self.overrideredirect(True)
        self.configure(bg=BORD_MED)
        self.resizable(False, False)

        container = tk.Frame(self, bg=BG_CARD, padx=28, pady=24)
        container.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Header: Title + Close button
        hdr = tk.Frame(container, bg=BG_CARD)
        hdr.pack(fill=tk.X, pady=(0, 16))

        tk.Label(hdr, text="Settings", font=_font(13, True), bg=BG_CARD, fg=TXT_PRI).pack(side=tk.LEFT)
        btn_close = tk.Label(hdr, text="✕", font=_font(11), bg=BG_CARD, fg=TXT_SEC, cursor="hand2", padx=6, pady=2)
        btn_close.pack(side=tk.RIGHT)
        btn_close.bind("<Enter>", lambda _: btn_close.configure(fg=TXT_PRI, bg=BG_HOVER))
        btn_close.bind("<Leave>", lambda _: btn_close.configure(fg=TXT_SEC, bg=BG_CARD))
        btn_close.bind("<Button-1>", lambda _: self.destroy())

        # Section 1: Device Connection
        self._build_section_header(container, "DEVICE & BLUETOOTH")
        dev_card = tk.Frame(container, bg=BG_PAGE, padx=16, pady=12, highlightthickness=1, highlightbackground=BORD_SUB)
        dev_card.pack(fill=tk.X, pady=(0, 16))

        # Status row
        st_row = tk.Frame(dev_card, bg=BG_PAGE)
        st_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(st_row, text="Status", font=_font(9, True), bg=BG_PAGE, fg=TXT_PRI).pack(side=tk.LEFT)

        if is_connected is True:
            st_text = f"Connected  ({battery}%)" if battery is not None else "Connected"
            st_bg, st_fg = "#E6F4EA", "#137333"
        elif is_connected is None:
            st_text = "Connecting..."
            st_bg, st_fg = "#FEF7E0", "#B06000"
        else:
            st_text = "Disconnected"
            st_bg, st_fg = "#F1F1EF", "#787774"

        tk.Label(st_row, text=f"• {st_text}", font=_font(8, True), bg=st_bg, fg=st_fg, padx=8, pady=2).pack(side=tk.RIGHT)

        # MAC Address input & Reconnect row
        mac_row = tk.Frame(dev_card, bg=BG_PAGE)
        mac_row.pack(fill=tk.X, pady=(4, 6))

        tk.Label(mac_row, text="MAC Address:", font=_font(9), bg=BG_PAGE, fg=TXT_SEC).pack(side=tk.LEFT, padx=(0, 8))
        self.mac_var = tk.StringVar(value=mac_address)
        mac_entry = tk.Entry(mac_row, textvariable=self.mac_var, font=_font(9), bg=BG_CARD, fg=TXT_PRI, relief=tk.FLAT, width=20)
        mac_entry.pack(side=tk.LEFT, padx=(0, 10), ipady=3)

        btn_retry = tk.Label(
            mac_row, text="Retry Connection",
            font=_font(8, True), bg=TXT_PRI, fg=TXT_INV,
            padx=12, pady=4, cursor="hand2",
        )
        btn_retry.pack(side=tk.RIGHT)
        btn_retry.bind("<Enter>", lambda _: btn_retry.configure(bg="#1A1A1A"))
        btn_retry.bind("<Leave>", lambda _: btn_retry.configure(bg=TXT_PRI))
        btn_retry.bind("<Button-1>", lambda _: self._handle_retry())

        tk.Label(
            dev_card,
            text="Tip: Make sure tablet is awake (touch stylus to paper or press page button).",
            font=_font(7), bg=BG_PAGE, fg=TXT_TER, anchor="w",
        ).pack(fill=tk.X, pady=(4, 0))

        # Section 2: Library & Storage
        self._build_section_header(container, "DOCUMENT LIBRARY")
        lib_card = tk.Frame(container, bg=BG_PAGE, padx=16, pady=12, highlightthickness=1, highlightbackground=BORD_SUB)
        lib_card.pack(fill=tk.X, pady=(0, 16))

        lib_info = tk.Frame(lib_card, bg=BG_PAGE)
        lib_info.pack(fill=tk.X)
        tk.Label(lib_info, text=f"Total Indexed Documents:  {total_notes_count}", font=_font(9, True), bg=BG_PAGE, fg=TXT_PRI).pack(side=tk.LEFT)

        btn_rescan = tk.Label(
            lib_info, text="Rescan Library",
            font=_font(8), bg=BG_WELL, fg=TXT_PRI,
            padx=10, pady=3, cursor="hand2",
        )
        btn_rescan.pack(side=tk.RIGHT)
        btn_rescan.bind("<Enter>", lambda _: btn_rescan.configure(bg=BG_ACTIVE))
        btn_rescan.bind("<Leave>", lambda _: btn_rescan.configure(bg=BG_WELL))
        btn_rescan.bind("<Button-1>", lambda _: (self.on_rescan_library(), self.destroy()))

        tk.Label(
            lib_card,
            text="Scanned: ~/HuionNotes, ./notes_output, ./exported_notes",
            font=_font(8), bg=BG_PAGE, fg=TXT_SEC, anchor="w",
        ).pack(fill=tk.X, pady=(4, 0))

        # Section 3: Interface & Logging
        self._build_section_header(container, "INTERFACE & LOGGING")
        ui_card = tk.Frame(container, bg=BG_PAGE, padx=16, pady=12, highlightthickness=1, highlightbackground=BORD_SUB)
        ui_card.pack(fill=tk.X, pady=(0, 16))

        log_row = tk.Frame(ui_card, bg=BG_PAGE)
        log_row.pack(fill=tk.X)
        tk.Label(log_row, text="Activity Log Console:", font=_font(9), bg=BG_PAGE, fg=TXT_SEC).pack(side=tk.LEFT)

        self.log_var = tk.BooleanVar(value=show_log)
        chk_log = tk.Checkbutton(
            log_row, text="Show terminal at bottom of window",
            variable=self.log_var, font=_font(8),
            bg=BG_PAGE, fg=TXT_PRI, activebackground=BG_PAGE,
            command=self._on_toggle_log_chk,
        )
        chk_log.pack(side=tk.RIGHT)

        # Section 4: AI & OCR
        self._build_section_header(container, "AI / HTR TRANSCRIPTION")
        ai_card = tk.Frame(container, bg=BG_PAGE, padx=16, pady=12, highlightthickness=1, highlightbackground=BORD_SUB)
        ai_card.pack(fill=tk.X, pady=(0, 18))

        key_row = tk.Frame(ai_card, bg=BG_PAGE)
        key_row.pack(fill=tk.X)
        tk.Label(key_row, text="Gemini API Key:", font=_font(9), bg=BG_PAGE, fg=TXT_SEC).pack(side=tk.LEFT, padx=(0, 8))

        import os
        current_key = os.environ.get("GEMINI_API_KEY", "")
        self.key_var = tk.StringVar(value=current_key)
        key_entry = tk.Entry(key_row, textvariable=self.key_var, font=_font(9), bg=BG_CARD, fg=TXT_PRI, relief=tk.FLAT, show="•", width=22)
        key_entry.pack(side=tk.LEFT, padx=(0, 10), ipady=3)

        btn_save_key = tk.Label(
            key_row, text="Save Key",
            font=_font(8), bg=BG_WELL, fg=TXT_PRI,
            padx=10, pady=3, cursor="hand2",
        )
        btn_save_key.pack(side=tk.RIGHT)
        btn_save_key.bind("<Enter>", lambda _: btn_save_key.configure(bg=BG_ACTIVE))
        btn_save_key.bind("<Leave>", lambda _: btn_save_key.configure(bg=BG_WELL))
        btn_save_key.bind("<Button-1>", lambda _: self._save_key())

        # Footer: Disclaimer & Done button
        footer = tk.Frame(container, bg=BG_CARD)
        footer.pack(fill=tk.X, pady=(6, 0))

        tk.Label(
            footer,
            text="Unofficial community project. Not affiliated with Shenzhen Huion Animation Technology Co., Ltd.",
            font=_font(7), bg=BG_CARD, fg=TXT_TER, anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        btn_done = tk.Label(
            footer, text="Done",
            font=_font(9, True), bg=TXT_PRI, fg=TXT_INV,
            padx=20, pady=6, cursor="hand2",
        )
        btn_done.pack(side=tk.RIGHT)
        btn_done.bind("<Enter>", lambda _: btn_done.configure(bg="#1A1A1A"))
        btn_done.bind("<Leave>", lambda _: btn_done.configure(bg=TXT_PRI))
        btn_done.bind("<Button-1>", lambda _: self.destroy())

        self.bind("<Escape>", lambda _: self.destroy())

        # Center on parent
        self.update_idletasks()
        pw = parent.winfo_width() or 900
        ph = parent.winfo_height() or 650
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        h = self.winfo_reqheight() or 460
        self.geometry(f"{width}x{h}+{px + (pw - width)//2}+{py + (ph - h)//2}")

        self.transient(parent)
        self.grab_set()
        parent.wait_window(self)

    def _on_toggle_log_chk(self) -> None:
        if self.on_toggle_log:
            self.on_toggle_log(self.log_var.get())

    def _build_section_header(self, parent: tk.Widget, title: str) -> None:
        tk.Label(
            parent, text=title,
            font=_font(8, True), bg=BG_CARD, fg=TXT_TER,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 4))

    def _handle_retry(self) -> None:
        mac = self.mac_var.get().strip() or self.mac_address
        self.on_retry_connect(mac)
        self.destroy()

    def _save_key(self) -> None:
        key = self.key_var.get().strip()
        if key:
            self.on_save_gemini_key(key)


# ── Modern Markdown Viewer Dialog ────────────────────────────────────────────

class ModernMarkdownViewerDialog(tk.Toplevel):
    """Clean modal viewer for transcribed Markdown notes."""

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        title: str,
        md_path: str,
        width: int = 680,
        height: int = 560,
    ) -> None:
        super().__init__(parent)
        self.md_path = md_path

        self.overrideredirect(True)
        self.configure(bg=BORD_MED)
        self.resizable(False, False)

        container = tk.Frame(self, bg=BG_CARD, padx=24, pady=20)
        container.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Header
        hdr = tk.Frame(container, bg=BG_CARD)
        hdr.pack(fill=tk.X, pady=(0, 10))

        tk.Label(hdr, text=title, font=_font(12, True), bg=BG_CARD, fg=TXT_PRI).pack(side=tk.LEFT)
        btn_close = tk.Label(hdr, text="✕", font=_font(11), bg=BG_CARD, fg=TXT_SEC, cursor="hand2", padx=6, pady=2)
        btn_close.pack(side=tk.RIGHT)
        btn_close.bind("<Enter>", lambda _: btn_close.configure(fg=TXT_PRI, bg=BG_HOVER))
        btn_close.bind("<Leave>", lambda _: btn_close.configure(fg=TXT_SEC, bg=BG_CARD))
        btn_close.bind("<Button-1>", lambda _: self.destroy())

        # Path row
        path_row = tk.Frame(container, bg=BG_PAGE, padx=10, pady=6, highlightthickness=1, highlightbackground=BORD_SUB)
        path_row.pack(fill=tk.X, pady=(0, 12))

        tk.Label(path_row, text=md_path, font=_font(8), bg=BG_PAGE, fg=TXT_SEC, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

        import subprocess
        btn_open = tk.Label(path_row, text="Open File", font=_font(8, True), bg=BG_WELL, fg=TXT_PRI, padx=8, pady=2, cursor="hand2")
        btn_open.pack(side=tk.RIGHT)
        btn_open.bind("<Enter>", lambda _: btn_open.configure(bg=BG_ACTIVE))
        btn_open.bind("<Leave>", lambda _: btn_open.configure(bg=BG_WELL))
        btn_open.bind("<Button-1>", lambda _: subprocess.Popen(["xdg-open", md_path]))

        # Text container
        text_wrap = tk.Frame(container, bg=BG_CARD, highlightthickness=1, highlightbackground=BORD_SUB)
        text_wrap.pack(fill=tk.BOTH, expand=True, pady=(0, 14))

        from pathlib import Path
        content = Path(md_path).read_text(encoding="utf-8", errors="ignore") if Path(md_path).exists() else "*File not found.*"

        text_widget = tk.Text(
            text_wrap, font=("monospace", 9),
            bg=BG_PAGE, fg=TXT_PRI,
            padx=14, pady=12, relief=tk.FLAT, bd=0,
            wrap=tk.WORD,
        )
        text_widget.insert(tk.END, content)
        text_widget.config(state=tk.DISABLED)

        scrollbar = ModernScrollbar(text_wrap, target_canvas=text_widget, width=8, bg=BG_PAGE)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Footer Done button
        btn_done = tk.Label(
            container, text="Done",
            font=_font(9, True), bg=TXT_PRI, fg=TXT_INV,
            padx=18, pady=6, cursor="hand2",
        )
        btn_done.pack(side=tk.RIGHT)
        btn_done.bind("<Enter>", lambda _: btn_done.configure(bg="#1A1A1A"))
        btn_done.bind("<Leave>", lambda _: btn_done.configure(bg=TXT_PRI))
        btn_done.bind("<Button-1>", lambda _: self.destroy())

        self.bind("<Escape>", lambda _: self.destroy())

        # Center on parent
        self.update_idletasks()
        pw = parent.winfo_width() or 900
        ph = parent.winfo_height() or 650
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        self.geometry(f"{width}x{height}+{px + (pw - width)//2}+{py + (ph - height)//2}")

        self.transient(parent)
        self.grab_set()
        parent.wait_window(self)
