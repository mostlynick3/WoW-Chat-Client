# -*- mode: python ; coding: utf-8 -*-
# Frozen build for the WoW Chat desktop client.
#
# Built via build/build-all.sh or CI — never extend by hand with extra
# CLI flags; everything lives here so all OSes build identically.
# (Only hooksconfig can tame the stock gi/Gst hooks — there is no CLI
# equivalent — which is why this is a spec file and not a long command.)
import os
import sys

from PyInstaller.utils.hooks import collect_all

# All paths below anchor at the repo root (bare relative paths would
# resolve against build/ instead). SPECPATH is the spec's own dir.
ROOT = os.path.dirname(SPECPATH)
BUILD = os.path.join(ROOT, "build")

# Per-OS binary icon (Linux ELFs carry none; the AppImage/.desktop
# entry provides the icon there instead).
if sys.platform == "win32":
    icon_file = os.path.join(BUILD, "icon.ico")
    console = False  # no console window next to the app
elif sys.platform == "darwin":
    icon_file = os.path.join(BUILD, "icon.icns")
    console = False
else:
    icon_file = None
    console = True  # Linux users run this from a console to see errors

# The build machine's site-packages leaks into the binary via pywebview's
# backend imports — exclude the toolkits/data libs we never use.
# (Linux desktop runs on system GTK/WebKit, not bundled Qt.)
EXCLUDES = [
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    "numpy", "pandas", "scipy", "matplotlib",
    "pygame", "PIL", "tkinter", "jnius",
    # pywebview only needs this for self-signed HTTPS certs; the app
    # serves plain HTTP (and degrades cleanly without it).
    "cryptography",
]

# PyGObject bridge (gi/__init__, importer, overrides). Absent on
# Windows/macOS builders — skipped there, the window backends there
# are system WebView2/WKWebView and need no gi.
try:
    gi_datas, gi_binaries, gi_hidden = collect_all("gi")
except Exception:
    gi_datas, gi_binaries, gi_hidden = [], [], []

a = Analysis(
    [os.path.join(ROOT, "desktop.py")],
    pathex=[],
    binaries=gi_binaries,
    datas=[(os.path.join(ROOT, "web"), "web")] + gi_datas,
    hiddenimports=gi_hidden,
    hookspath=[os.path.join(BUILD, "pyinstaller-hooks")],
    hooksconfig={
        # Stock gi.repository.Gtk hook: no bundled icon/theme dirs
        # (every cursor theme on the builder ≈ 1GB); the window uses
        # host GTK data. Typelibs are still collected.
        "gi": {"icons": [], "themes": [], "languages": ["en"]},
        # Stock gi.repository.Gst hook: no plugin glob (chat has no
        # media); typelib data is still collected for WebKit2 deps.
        "gstreamer": {"include_plugins": []},
    },
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="wow-chat-desktop",
    debug=False,
    strip=False,
    upx=False,
    console=console,  # windowed on win/mac, console on linux
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
