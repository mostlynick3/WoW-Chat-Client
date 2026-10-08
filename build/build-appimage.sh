#!/usr/bin/env bash
# Assemble the Linux AppImage from dist/wow-chat-desktop.
# Needs: curl. appimagetool is fetched on first run.
# (appimagetool itself runs via APPIMAGE_EXTRACT_AND_RUN, no FUSE needed
# to BUILD; running the result needs FUSE on the target system.)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x dist/wow-chat-desktop ] || {
  echo "build dist/wow-chat-desktop first (build/build-all.sh)" >&2
  exit 1
}
APPDIR=WoW-Chat-Client.AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp dist/wow-chat-desktop "$APPDIR/usr/bin/"
cp build/appimage/AppRun "$APPDIR/AppRun"
cp build/appimage/WoW-Chat-Client.desktop "$APPDIR/"
cp build/appimage/WoW-Chat-Client.png "$APPDIR/"
chmod +x "$APPDIR/AppRun" "$APPDIR/usr/bin/wow-chat-desktop"
TOOL=build/appimagetool-x86_64.AppImage
if [ ! -x "$TOOL" ]; then
  curl -sL -o "$TOOL" \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi
export APPIMAGE_EXTRACT_AND_RUN=1
ARCH=x86_64 "$TOOL" "$APPDIR"
# appimagetool derives the name from the desktop entry (underscored).
mv -f WoW_Chat_Client-x86_64.AppImage WoW-Chat-Client-linux-x86_64.AppImage
echo "done: WoW-Chat-Client-linux-x86_64.AppImage"
