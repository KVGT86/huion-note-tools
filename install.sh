#!/usr/bin/env bash
set -e

# ==============================================================================
# HuionNote Installation & Setup Script
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "           HuionNote Setup & Installation               "
echo "========================================================"

# 1. Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "[!] Error: Python 3 is required but not installed."
    exit 1
fi

PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[✓] Found Python $PYTHON_VER"

# 2. Virtual Environment Setup
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating virtual environment at .venv..."
    python3 -m venv "$VENV_DIR"
fi

echo "[*] Upgrading pip and build tools..."
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel --quiet

echo "[*] Installing dependencies..."
"$VENV_DIR/bin/pip" install -e . --quiet

# 3. Create Default Notes Storage Directory (~/HuionNotes)
NOTES_DIR="$HOME/HuionNotes"
mkdir -p "$NOTES_DIR"
echo "[✓] Notes directory ready at $NOTES_DIR"

# 4. Install Application Icon
ICON_SRC="$SCRIPT_DIR/assets/huionnote.png"
ICON_DEST_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
mkdir -p "$ICON_DEST_DIR"
mkdir -p "$HOME/.local/share/pixmaps"

if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$ICON_DEST_DIR/huionnote.png"
    cp "$ICON_SRC" "$HOME/.local/share/pixmaps/huionnote.png"
    echo "[✓] App icon installed to $ICON_DEST_DIR/huionnote.png"
    if command -v gtk-update-icon-cache &> /dev/null; then
        gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    fi
fi

# 5. Install Desktop Launcher (.desktop)
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
DESKTOP_FILE="$DESKTOP_DIR/huionnote.desktop"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=HuionNote
GenericName=Digital Notebook Companion
Comment=Huion Note X10 Companion & Digital Notebook
Exec=env QT_QPA_PLATFORM=xcb $VENV_DIR/bin/python3 $SCRIPT_DIR/start_app.py
Icon=$ICON_DEST_DIR/huionnote.png
Terminal=false
Categories=Utility;Graphics;Office;
StartupWMClass=huionnote
Keywords=huion;note;tablet;handwriting;drawing;digital;
EOF

chmod +x "$DESKTOP_FILE"
chmod +x "$SCRIPT_DIR/start_app.py"

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo "[✓] Desktop launcher installed to $DESKTOP_FILE"
echo ""
echo "========================================================"
echo " Installation Complete!"
echo " • You can now launch HuionNote from your Application Menu/Dock,"
echo "   or run:  $SCRIPT_DIR/start_app.py"
echo " • To change the app icon art: replace assets/huionnote.png"
echo "   and rerun ./install.sh"
echo "========================================================"
