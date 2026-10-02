#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-$ROOT/build/AI Touch Bar.app}"
if [[ -e "$TARGET" ]]; then
  echo "Build already exists: $TARGET" >&2
  echo "Move that exact build artifact aside before rebuilding." >&2
  exit 2
fi

mkdir -p "$(dirname "$TARGET")"
STAGING="$(mktemp -d "$(dirname "$TARGET")/.touchbar-build.XXXXXX")"
APP="$STAGING/AI Touch Bar.app"
RES="$APP/Contents/Resources"
BIN="$APP/Contents/MacOS/TouchBarNativeLive"
MACHINE_ARCH="$(uname -m)"
case "$MACHINE_ARCH" in
  arm64|x86_64) ;;
  *) echo "Unsupported build architecture: $MACHINE_ARCH" >&2; exit 1 ;;
esac
cleanup() { [[ ! -d "$STAGING" ]] || /bin/rm -rf "$STAGING"; }
trap cleanup EXIT

mkdir -p "$APP/Contents/MacOS" "$RES/helper/vendor/usage" "$RES/status-assets"
cp "$ROOT/Info.plist" "$APP/Contents/Info.plist"
cp "$ROOT/Assets/menubar-pin.svg" "$ROOT/Assets/AppIcon.icns" "$RES/"
cp "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$ROOT/UPSTREAM-LICENSE" "$RES/"
cp "$ROOT/helper/quota_bridge.py" "$ROOT/helper/status_bridge.py" \
  "$ROOT/helper/agent_status.py" "$ROOT/helper/quota_touchbar.py" "$RES/helper/"
cp "$ROOT/helper/vendor/LICENSE" "$RES/helper/vendor/LICENSE"
cp "$ROOT/helper/vendor/usage/"*.py "$RES/helper/vendor/usage/"
cp "$ROOT/status-assets/"*.json "$RES/status-assets/"

swiftc -swift-version 5 -O -target "$MACHINE_ARCH-apple-macos13.0" -framework AppKit \
  -module-cache-path "${TMPDIR:-/private/tmp}/ai-touchbar-module-cache" \
  "$ROOT/Sources/ControlStrip.swift" "$ROOT/Sources/StatusDemo.swift" \
  "$ROOT/Sources/AgentState.swift" "$ROOT/Sources/LiveStatusReader.swift" \
  "$ROOT/Sources/PrototypeChecks.swift" "$ROOT/Sources/QuotaReader.swift" \
  "$ROOT/Sources/TouchBarUI.swift" "$ROOT/Sources/NativeUI.swift" \
  "$ROOT/Sources/main.swift" -o "$BIN"
codesign --force --deep --sign - "$APP"
mv "$APP" "$TARGET"
echo "Built: $TARGET"
