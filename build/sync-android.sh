#!/usr/bin/env bash
# Refresh the Android-bundled Python copy from the repo sources.
# Run after changing app/, wow/, web/ or config.example.json.
# (CI runs this too, so the APK never goes stale.)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=android/app/src/main/python
rm -rf "$PY/app" "$PY/wow" "$PY/web"
cp -r app "$PY/app"
cp -r wow "$PY/wow"
cp -r web "$PY/web"
cp config.example.json "$PY/"
rm -f "$PY/app/build_info.py"
find "$PY" -name __pycache__ -type d -prune -exec rm -rf {} +
echo "synced: $PY"
