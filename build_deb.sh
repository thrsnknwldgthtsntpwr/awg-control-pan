#!/bin/bash
# Build awg-panel .deb (run on Ubuntu/Debian with dpkg-deb).
# Usage: ./build_deb.sh [version]
set -euo pipefail
VER="${1:-0.1.0}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
STAGE="$ROOT/dist/awg-panel_${VER}_all"
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" \
  "$STAGE/usr/share/awg-panel/src/awg_panel" \
  "$STAGE/usr/sbin" \
  "$STAGE/lib/systemd/system" \
  "$STAGE/etc/sudoers.d" \
  "$STAGE/etc/awg-panel"

sed "s/^Version:.*/Version: $VER/" "$ROOT/packaging/DEBIAN/control" > "$STAGE/DEBIAN/control"
cp "$ROOT/packaging/DEBIAN/conffiles" "$STAGE/DEBIAN/"
cp "$ROOT/packaging/DEBIAN/postinst" "$ROOT/packaging/DEBIAN/prerm" "$ROOT/packaging/DEBIAN/postrm" "$STAGE/DEBIAN/"
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm" "$STAGE/DEBIAN/postrm"

cp -r "$ROOT/src/awg_panel/." "$STAGE/usr/share/awg-panel/src/awg_panel/"
cp "$ROOT/bin/awg-panel-helper" "$STAGE/usr/sbin/awg-panel-helper"
cp "$ROOT/bin/awg-panel-set-password" "$STAGE/usr/sbin/awg-panel-set-password"
cp "$ROOT/bin/awg-panel-set-password-internal" "$STAGE/usr/sbin/awg-panel-set-password-internal"
chmod 755 "$STAGE/usr/sbin/awg-panel-helper" "$STAGE/usr/sbin/awg-panel-set-password" "$STAGE/usr/sbin/awg-panel-set-password-internal"

cp "$ROOT/packaging/awg-panel.service" "$STAGE/lib/systemd/system/"
cp "$ROOT/packaging/sudoers" "$STAGE/etc/sudoers.d/awg-panel"
chmod 440 "$STAGE/etc/sudoers.d/awg-panel"
cp "$ROOT/packaging/config.ini.example" "$STAGE/usr/share/awg-panel/config.ini.example"

# conffile placeholder so dpkg sees the path (real file created in postinst if missing)
touch "$STAGE/etc/awg-panel/.placeholder" 2>/dev/null || true

dpkg-deb --build "$STAGE"
echo "Built: $STAGE.deb"
