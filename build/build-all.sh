#!/usr/bin/env bash
# Build single-file executables with PyInstaller for the current OS.
# Repeat on each target OS (macOS / Windows / Linux) — or see dist/ CI notes.
#
# Both targets are supported:
#   wow-chat-desktop  DISTRIBUTED binary (standalone app window, pywebview).
#                     This is what ships in GitHub releases.
#   wow-chat          headless/server use (chat via system browser).
#                     Built for completeness, not distributed.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install --upgrade pip pyinstaller flask
# Web mode (browser UI)
python3 -m PyInstaller --noconfirm --onefile --name wow-chat \
  --add-data "web:web" run.py
# Desktop mode (pywebview window when available).
# Everything (excludes, hooks, per-OS icon) lives in the spec file —
# build-machine site-packages would otherwise leak Qt/numpy/cursors
# into the binary (~500MB) and stock gi/Gst hooks bundle ~1GB of
# themes/plugins. Linux desktop runs on system GTK/WebKit, not Qt.
python3 -m pip install pywebview || true
python3 -m PyInstaller --noconfirm build/wow-chat-desktop.spec
echo "done: dist/wow-chat[.exe]  dist/wow-chat-desktop[.exe]"
echo "linux release packaging: build/build-appimage.sh"
