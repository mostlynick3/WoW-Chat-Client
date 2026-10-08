#!/usr/bin/env bash
# Build single-file executables with PyInstaller for the current OS.
# Repeat on each target OS (macOS / Windows / Linux) — or see dist/ CI notes.
#
# Both targets are supported:
#   ygg-chat-desktop  DISTRIBUTED binary (standalone app window, pywebview).
#                     This is what ships in GitHub releases.
#   ygg-chat          headless/server use (chat via system browser).
#                     Built for completeness, not distributed.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install --upgrade pip pyinstaller flask
# Web mode (browser UI)
python3 -m PyInstaller --noconfirm --onefile --name ygg-chat \
  --add-data "web:web" run.py
# Desktop mode (pywebview window when available)
python3 -m pip install pywebview || true
python3 -m PyInstaller --noconfirm --onefile --name ygg-chat-desktop \
  --add-data "web:web" desktop.py
echo "done: dist/ygg-chat[.exe]  dist/ygg-chat-desktop[.exe]"
