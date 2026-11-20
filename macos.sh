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
        echo "Run ./macos.sh to open HuionNote."
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
        exec .venv/bin/huionnote
        ;;
    *)
        echo "Usage: ./macos.sh [setup | huion COMMAND | test [PYTEST_OPTIONS]]" >&2
        exit 2
        ;;
esac
