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
# Desktop mode (pywebview window when available).
# NOTE: the build machine's site-packages leaks into the binary via
# pywebview's backend imports — exclude the toolkits/data libs we never
# use (Linux desktop runs on system GTK/WebKit, not bundled Qt).
# Without this the binary balloons to ~500MB of Qt5/Qt6/numpy/pandas.
# A second ~1GB blowup (every cursor/icon theme on the build machine)
# comes from PyInstaller's stock gi.repository.Gtk hook; the override in
# build/pyinstaller-hooks trims it to typelib data only.
DESKTOP_EXCLUDES="--exclude-module PyQt5 --exclude-module PyQt6 \
  --exclude-module PySide2 --exclude-module PySide6 --exclude-module wx \
  --exclude-module numpy --exclude-module pandas --exclude-module scipy \
  --exclude-module matplotlib --exclude-module pygame --exclude-module PIL \
  --exclude-module tkinter"
# Binary icon (ELF binaries carry no icon; Linux uses the AppImage +
# .desktop entry instead — see build/build-appimage.sh).
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*|Windows_NT) ICON_ARG="--icon build/icon.ico" ;;
  Darwin) ICON_ARG="--icon build/icon.icns" ;;
  *) ICON_ARG="" ;;
esac
python3 -m pip install pywebview || true
# shellcheck disable=SC2086
python3 -m PyInstaller --noconfirm --onefile --name ygg-chat-desktop \
  $DESKTOP_EXCLUDES $ICON_ARG \
  --additional-hooks-dir build/pyinstaller-hooks \
  --add-data "web:web" desktop.py
echo "done: dist/ygg-chat[.exe]  dist/ygg-chat-desktop[.exe]"
echo "linux release packaging: build/build-appimage.sh"
