"""System tray indicator for HuionNote on Linux / Zorin OS.

Shows real-time connection status and battery percentage in the system tray.
"""
from __future__ import annotations

import threading
from typing import Optional, Callable
from PIL import Image, ImageDraw


from pathlib import Path


def _create_tray_icon(is_connected: Optional[bool], battery: Optional[int] = None) -> Image.Image:
    """Generate a clean 64x64 tray icon with blue (connected) or red (disconnected) status dot.

    Uses assets/huionnote.png if available, with a clean vector pen fallback.
    """
    size = 64

    # 1. Try loading custom icon art
    icon_art_path = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "huionnote.png"
    if not icon_art_path.exists():
        icon_art_path = Path(__file__).resolve().parent.parent.parent / "assets" / "huionnote.png"

    if icon_art_path.exists():
        try:
            base_img = Image.open(icon_art_path).convert("RGBA")
            img = base_img.resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    else:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    draw = ImageDraw.Draw(img)

    # If fallback empty image, draw vector pen
    if not icon_art_path.exists():
        barrel = [(44, 8), (56, 20), (28, 48), (16, 36)]
        draw.polygon(barrel, fill="#FFFFFF", outline="#1F2937", width=2)
        draw.line([(32, 28), (44, 40)], fill="#9CA3AF", width=3)
        draw.line([(24, 36), (36, 48)], fill="#9CA3AF", width=2)
        nib = [(16, 36), (28, 48), (8, 56)]
        draw.polygon(nib, fill="#1F2937", outline="#111827", width=2)
        draw.line([(10, 54), (8, 56)], fill="#D4AF37", width=2)

    # Status dot (bottom-right corner)
    # Blue if connected, Yellow if connecting, Red if disconnected
    if is_connected is True:
        dot_color = "#2563EB"
    elif is_connected is None:
        dot_color = "#F59E0B"
    else:
        dot_color = "#EF4444"

    # Outer border ring for crisp contrast on light or dark panel themes
    draw.ellipse([40, 40, 62, 62], fill="#1F2937")
    draw.ellipse([43, 43, 59, 59], fill=dot_color)

    return img


class HuionNoteTray:
    """Manages the background system tray icon and menu."""

    def __init__(
        self,
        on_show: Optional[Callable[[], None]] = None,
        on_sync: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
    ) -> None:
        self.on_show = on_show
        self.on_sync = on_sync
        self.on_quit = on_quit

        self._tray_icon = None
        self._is_connected: Optional[bool] = False
        self._battery: Optional[int] = None
        self._started = False

    def start(self) -> None:
        """Start the system tray icon in a daemon thread."""
        try:
            import pystray
        except ImportError:
            return

        def _setup(icon):
            icon.visible = True

        image = _create_tray_icon(self._is_connected, self._battery)
        menu = self._build_menu()

        self._tray_icon = pystray.Icon(
            name="HuionNote",
            icon=image,
            title="HuionNote",
            menu=menu,
        )

        def _run():
            try:
                self._tray_icon.run(setup=_setup)
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()
        self._started = True

    def _build_menu(self):
        try:
            import pystray
        except ImportError:
            return None

        # Build dynamic title
        if self._is_connected is True:
            status_text = f"HuionNote: Connected ({self._battery}%)" if self._battery is not None else "HuionNote: Connected"
        elif self._is_connected is None:
            status_text = "HuionNote: Connecting..."
        else:
            status_text = "HuionNote: Disconnected"

        items = [
            pystray.MenuItem(status_text, lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open HuionNote", lambda: self._handle_show()),
            pystray.MenuItem("Sync Now", lambda: self._handle_sync()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self._handle_quit()),
        ]
        return pystray.Menu(*items)

    def update_status(self, is_connected: Optional[bool], battery: Optional[int]) -> None:
        """Update connection state, battery percentage, icon badge, and tooltip."""
        self._is_connected = is_connected
        self._battery = battery

        if not self._tray_icon or not self._started:
            return

        try:
            # Update icon image
            self._tray_icon.icon = _create_tray_icon(is_connected, battery)

            # Update tooltip title
            if is_connected is True:
                batt_str = f" ({battery}%)" if battery is not None else ""
                self._tray_icon.title = f"HuionNote: Connected{batt_str}"
            elif is_connected is None:
                self._tray_icon.title = "HuionNote: Connecting..."
            else:
                self._tray_icon.title = "HuionNote: Disconnected"

            # Update menu
            self._tray_icon.menu = self._build_menu()
        except Exception:
            pass

    def _handle_show(self) -> None:
        if self.on_show:
            self.on_show()

    def _handle_sync(self) -> None:
        if self.on_sync:
            self.on_sync()

    def _handle_quit(self) -> None:
        self.stop()
        if self.on_quit:
            self.on_quit()

    def stop(self) -> None:
        """Stop the tray icon."""
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
            self._started = False
