#!/bin/bash
# Build dist/ApexCompanion.app + dist/ApexCompanion.zip from the repo. Run from anywhere:
#   bash packaging/build_app.sh        (on a clean, tagged commit: git tag v0.2.0)
#   APEX_VERSION=0.0.0-test APEX_ALLOW_DIRTY=1 bash packaging/build_app.sh   (local test build)
# Needs (build machine only): swiftc (Xcode Command Line Tools). Optional: the repo .venv with
# Pillow for the icon (or APEX_BUILD_PY=/path/to/python). End users need none of this.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/packaging"
DIST="$ROOT/dist"
APP="$DIST/ApexCompanion.app"

# A release must be reproducible from its tag: no uncommitted changes, version taken from the tag.
if [ "${APEX_ALLOW_DIRTY:-0}" != 1 ]; then
    dirty="$(git -C "$ROOT" status --porcelain)" \
        || { echo "error: can't read git status (not a git checkout?); set APEX_ALLOW_DIRTY=1 to build anyway" >&2; exit 1; }
    if [ -n "$dirty" ]; then
        echo "error: uncommitted changes; commit or stash them, or set APEX_ALLOW_DIRTY=1 for a test build:" >&2
        echo "$dirty" >&2
        exit 1
    fi
fi
VERSION="${APEX_VERSION:-}"
if [ -z "$VERSION" ]; then
    tag="$(git -C "$ROOT" describe --tags --exact-match 2>/dev/null)" \
        || { echo "error: HEAD has no tag; tag the commit, e.g. git tag v0.2.0, or set APEX_VERSION" >&2; exit 1; }
    VERSION="${tag#v}"
fi
# Spliced into Info.plist XML below.
VERSION_RE='^[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.-]+)?$'
[[ "$VERSION" =~ $VERSION_RE ]] || { echo "error: version '$VERSION' is not like 1.2.3 or 1.2.3-rc1" >&2; exit 1; }
echo "→ version $VERSION"

rm -rf "$APP" "$DIST/ApexCompanion.zip" "$DIST/ApexCompanion.zip.sha256"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/app"

echo "→ compiling host binary"
swiftc -O -target arm64-apple-macos14.0 -o "$APP/Contents/MacOS/ApexCompanion" "$PKG/main.swift"

echo "→ copying app files"
for f in apex.py control.py gemma.py personas.py rules.py report.py; do
    [ -f "$ROOT/$f" ] || { echo "missing $ROOT/$f" >&2; exit 1; }
    cp "$ROOT/$f" "$APP/Contents/Resources/app/"
done
cp "$PKG/sites_onboard.py" "$APP/Contents/Resources/app/"
cp "$PKG/launcher.sh" "$PKG/constraints.txt" "$APP/Contents/Resources/"
chmod +x "$APP/Contents/Resources/launcher.sh"

ICON_KEY=""
ICON_PY="${APEX_BUILD_PY:-$ROOT/.venv/bin/python}"   # override for worktrees without their own .venv
if [ -x "$ICON_PY" ] && "$ICON_PY" -c "import PIL" 2>/dev/null; then
    echo "→ drawing icon"
    TMP="$(mktemp -d)"
    "$ICON_PY" "$PKG/make_icon.py" "$TMP/icon.png"
    mkdir "$TMP/AppIcon.iconset"
    for s in 16 32 128 256 512; do
        sips -z $s $s "$TMP/icon.png" --out "$TMP/AppIcon.iconset/icon_${s}x${s}.png" >/dev/null
        sips -z $((s * 2)) $((s * 2)) "$TMP/icon.png" --out "$TMP/AppIcon.iconset/icon_${s}x${s}@2x.png" >/dev/null
    done
    iconutil -c icns "$TMP/AppIcon.iconset" -o "$APP/Contents/Resources/AppIcon.icns"
    rm -rf "$TMP"
    ICON_KEY="<key>CFBundleIconFile</key><string>AppIcon</string>"
else
    echo "→ skipping icon (no Python with Pillow at $ICON_PY; set APEX_BUILD_PY)"
fi

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>com.apexcompanion.app</string>
  <key>CFBundleName</key><string>ApexCompanion</string>
  <key>CFBundleDisplayName</key><string>ApexCompanion</string>
  <key>CFBundleExecutable</key><string>ApexCompanion</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  $ICON_KEY
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSArchitecturePriority</key><array><string>arm64</string></array>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppleEventsUsageDescription</key><string>ApexCompanion shows its setup questions and coaching notifications using macOS dialogs.</string>
  <key>NSScreenCaptureUsageDescription</key><string>ApexCompanion looks at your screen every 10 seconds to tell whether you are working. Screenshots never leave this Mac and are deleted after each check.</string>
</dict>
</plist>
PLIST
plutil -lint "$APP/Contents/Info.plist" >/dev/null

echo "→ ad-hoc signing"
codesign --force --deep -s - "$APP"
codesign --verify --deep --strict "$APP" && echo "  signature ok"

echo "→ zipping"
(cd "$DIST" && ditto -c -k --keepParent ApexCompanion.app ApexCompanion.zip)
# Relative name inside the file: `shasum -a 256 -c ApexCompanion.zip.sha256` works from the download folder.
(cd "$DIST" && shasum -a 256 ApexCompanion.zip > ApexCompanion.zip.sha256)
ls -lh "$DIST/ApexCompanion.zip"
cat "$DIST/ApexCompanion.zip.sha256"
echo "built $APP"
