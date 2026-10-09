#!/usr/bin/env bash
# Build single-file executables with PyInstaller for the current OS.
# Repeat on each target OS (macOS / Windows / Linux) — or see dist/ CI notes.
#
# Desktop target only:
#   wow-chat-desktop  DISTRIBUTED binary (standalone app window, pywebview).
#                     This is what ships in GitHub releases.
# Headless use is plain source: python3 run.py (browser UI on :5950).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install --upgrade pip pyinstaller flask
# Desktop mode (pywebview window when available).
# Everything (excludes, hooks, per-OS icon) lives in the spec file —
# build-machine site-packages would otherwise leak Qt/numpy/cursors
# into the binary (~500MB) and stock gi/Gst hooks bundle ~1GB of
# themes/plugins. Linux desktop runs on system GTK/WebKit, not Qt.
python3 -m pip install pywebview || true
python3 -m PyInstaller --noconfirm build/wow-chat-desktop.spec
echo "done: dist/wow-chat-desktop[.exe]"
echo "linux release packaging: build/build-appimage.sh"
