# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path


project_root = Path(SPEC).resolve().parents[2]
cairo_library = Path(os.environ["HUION_CAIRO_PREFIX"]) / "lib/libcairo.2.dylib"

a = Analysis(
    [str(project_root / "start_app.py")],
    pathex=[str(project_root / "src")],
    binaries=[(str(cairo_library), ".")],
    datas=[
        (str(project_root / "assets"), "assets"),
        (
            str(project_root / "src/huion_note_pipeline/gui/icons"),
            "huion_note_pipeline/gui/icons",
        ),
    ],
    hiddenimports=[
        "bleak.backends.corebluetooth.client",
        "bleak.backends.corebluetooth.scanner",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["dbus_fast", "evdev"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HuionNote",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="HuionNote",
)
app = BUNDLE(
    coll,
    name="HuionNote.app",
    icon=str(project_root / "build/macos/HuionNote.icns"),
    bundle_identifier="com.kvgt86.huionnote",
    version="1.7.3",
    info_plist={
        "CFBundleDisplayName": "HuionNote",
        "CFBundleName": "HuionNote",
        "LSMinimumSystemVersion": "14.0",
        "NSBluetoothAlwaysUsageDescription": (
            "HuionNote uses Bluetooth to connect to your Huion Note X10, "
            "sync saved pages, and receive live pen input."
        ),
        "NSHighResolutionCapable": True,
    },
)
