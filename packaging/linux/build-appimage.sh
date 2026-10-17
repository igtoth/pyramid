#!/usr/bin/env bash
# Build the AppImage from the Nuitka standalone folder.
# Usage: build-appimage.sh <version> <nuitka .dist folder>
set -euo pipefail
VERSION="$1"; SRC="$2"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APPDIR="$ROOT/build/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib/pyramid" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$SRC/." "$APPDIR/usr/lib/pyramid/"
cp "$ROOT/packaging/linux/pyramid.desktop" "$APPDIR/pyramid.desktop"
cp "$ROOT/packaging/linux/pyramid.desktop" "$APPDIR/usr/share/applications/"
cp "$ROOT/assets/icon/pyramid-256.png" "$APPDIR/pyramid.png"
cp "$ROOT/assets/icon/pyramid-256.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/pyramid.png"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/pyramid/Pyramid" "$@"
RUN
chmod +x "$APPDIR/AppRun"
TOOL="$ROOT/build/appimagetool.AppImage"
if [ ! -x "$TOOL" ]; then
  curl -fsSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi
mkdir -p "$ROOT/dist"
ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$ROOT/dist/pyramid-$VERSION-linux-x86_64.AppImage"
rm -rf "$APPDIR"
