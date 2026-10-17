#!/usr/bin/env bash
# Package the Nuitka app bundle as a DMG.
# Usage: build-dmg.sh <version> <path to the .app Nuitka made> <arch label>
# Not notarized: the first launch needs right-click > Open
# (or: xattr -dr com.apple.quarantine /Applications/Pyramid.app).
set -euo pipefail
VERSION="$1"; SRC_APP="$2"; ARCH="$3"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$ROOT/build/dmg"
rm -rf "$STAGE"; mkdir -p "$STAGE" "$ROOT/dist"
cp -R "$SRC_APP" "$STAGE/Pyramid.app"
PLIST="$STAGE/Pyramid.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName Pyramid" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string Pyramid" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.ighor.pyramid" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.ighor.pyramid" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSHumanReadableCopyright string 'MIT License, Ighor Toth'" "$PLIST" 2>/dev/null || true
# ad-hoc signature, so Gatekeeper sees one consistent bundle
codesign --force --deep --sign - "$STAGE/Pyramid.app"
ln -s /Applications "$STAGE/Applications"
DMG="$ROOT/dist/pyramid-$VERSION-macos-$ARCH.dmg"
rm -f "$DMG"
for i in 1 2 3 4 5; do  # hdiutil sometimes answers "Resource busy" on CI runners
  hdiutil create -volname "Pyramid $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG" && break
  echo "hdiutil failed, retrying ($i)"; sleep 5
done
[ -f "$DMG" ]
rm -rf "$STAGE"
echo "built $DMG"
