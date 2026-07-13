# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — First Frame Extractor.

Un unico spec per macOS e Windows. Impacchetta interprete Python, PySide6 e il
binario ffmpeg statico (imageio-ffmpeg) in un eseguibile standalone (onefile).
Su macOS costruisce anche il bundle .app.
"""

import sys

from PyInstaller.utils.hooks import collect_data_files

# Include il binario ffmpeg statico fornito da imageio-ffmpeg.
datas = collect_data_files("imageio_ffmpeg")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["imageio_ffmpeg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

is_macos = sys.platform == "darwin"

if is_macos:
    # macOS: onedir + BUNDLE (.app). onefile e .app non convivono bene con la
    # sicurezza di macOS, quindi teniamo binaries/datas fuori dall'EXE.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="FirstFrameExtractor",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,  # app GUI: nessuna finestra console
        disable_windowed_traceback=False,
        argv_emulation=True,  # apertura file via drag sull'icona
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="FirstFrameExtractor",
    )
    app = BUNDLE(
        coll,
        name="First Frame Extractor.app",
        icon="assets/icon.icns",
        bundle_identifier="com.firstframeextractor.app",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleDisplayName": "First Frame Extractor",
            "CFBundleShortVersionString": "1.0.8",
            "CFBundleVersion": "1.0.8",
        },
    )
else:
    # Windows/Linux: onefile — binaries e datas dentro un unico eseguibile.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="FirstFrameExtractor",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        console=False,  # app GUI: nessuna finestra console
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon="assets/icon.ico",
    )
