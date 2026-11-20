#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
    echo "Run this script from a native Apple Silicon macOS Terminal." >&2
    exit 1
fi

# Homebrew's arm64 installation may be absent from the current shell PATH.
export PATH="/opt/homebrew/bin:$PATH"
if ! command -v brew >/dev/null; then
    echo "Install Apple Silicon Homebrew from https://brew.sh/ and run this script again." >&2
    exit 1
fi

if [[ "${1:-}" == setup ]]; then
    brew install python@3.13 python-tk@3.13 cairo
    "$(brew --prefix python@3.13)/bin/python3.13" -m venv .venv
    .venv/bin/python -m pip --disable-pip-version-check --no-input install -e '.[dev]'
    .venv/bin/python -m pip check
fi

if [[ ! -x .venv/bin/huionnote ]]; then
    echo "Run ./macos.sh setup first." >&2
    exit 1
fi

# CairoSVG loads Cairo at runtime. Include Homebrew's arm64 library directory.
cairo_prefix="$(brew --prefix cairo)"
export HUION_CAIRO_PREFIX="$cairo_prefix"
export DYLD_FALLBACK_LIBRARY_PATH="$cairo_prefix/lib:${DYLD_FALLBACK_LIBRARY_PATH:-/usr/local/lib:/usr/lib}"

case "${1:-}" in
    setup)
        .venv/bin/python - <<'PYTHON'
import cairosvg
import tkinter
from bleak.backends.corebluetooth.client import BleakClientCoreBluetooth
from PySide6.QtWidgets import QApplication

svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'
assert cairosvg.svg2png(bytestring=svg).startswith(b"\x89PNG")
PYTHON
        iconset_dir="build/macos/HuionNote.iconset"
        mkdir -p "$iconset_dir"
        for size in 16 32 128 256 512; do
            sips -z "$size" "$size" assets/huionnote-macos.png --out "$iconset_dir/icon_${size}x${size}.png" >/dev/null
            retina_size=$((size * 2))
            sips -z "$retina_size" "$retina_size" assets/huionnote-macos.png --out "$iconset_dir/icon_${size}x${size}@2x.png" >/dev/null
        done
        iconutil -c icns "$iconset_dir" -o build/macos/HuionNote.icns
        .venv/bin/pyinstaller --noconfirm --clean packaging/macos/HuionNote.spec

        user_applications_dir="$(.venv/bin/python -c 'from pathlib import Path; print(Path.home() / "Applications")')"
        installed_app="$user_applications_dir/HuionNote.app"
        mkdir -p "$user_applications_dir"
        INSTALLED_APP="$installed_app" .venv/bin/python - <<'PYTHON'
import os
import shutil
from pathlib import Path

installed_app = Path(os.environ["INSTALLED_APP"])
if installed_app.exists():
    shutil.rmtree(installed_app)
PYTHON
        ditto dist/HuionNote.app "$installed_app"
        codesign --force --deep --sign - "$installed_app"
        echo "HuionNote is installed at $installed_app"
        echo "Open it from Finder, Spotlight, or run ./macos.sh"
        ;;
    huion)
        shift
        exec .venv/bin/huion "$@"
        ;;
    test)
        shift
        exec .venv/bin/python -m pytest "$@"
        ;;
    "")
        installed_app="$(.venv/bin/python -c 'from pathlib import Path; print(Path.home() / "Applications" / "HuionNote.app")')"
        if [[ ! -d "$installed_app" ]]; then
            echo "Run ./macos.sh setup to install HuionNote.app first." >&2
            exit 1
        fi
        open "$installed_app"
        ;;
    *)
        echo "Usage: ./macos.sh [setup | huion COMMAND | test [PYTEST_OPTIONS]]" >&2
        exit 2
        ;;
esac
