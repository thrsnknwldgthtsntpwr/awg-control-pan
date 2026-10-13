#!/bin/bash
# Build awg-panel .deb (run on Ubuntu/Debian with dpkg-deb).
# Usage: ./build_deb.sh [version]
set -euo pipefail
VER="${1:-0.1.0}"
if [[ ! "$VER" =~ ^[0-9A-Za-z.+~:-]+$ ]]; then
  echo "bad version: $VER" >&2
  exit 1
fi
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
# Never ship bytecode: stale .pyc under /usr would shadow fixed .py on upgrade.
find "$STAGE/usr/share/awg-panel" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/usr/share/awg-panel" -name '*.py[co]' -delete 2>/dev/null || true
cp "$ROOT/bin/awg-panel-helper" "$STAGE/usr/sbin/awg-panel-helper"
cp "$ROOT/bin/awg-panel-set-password" "$STAGE/usr/sbin/awg-panel-set-password"
chmod 755 "$STAGE/usr/sbin/awg-panel-helper" "$STAGE/usr/sbin/awg-panel-set-password"

cp "$ROOT/packaging/awg-panel.service" "$STAGE/lib/systemd/system/"
cp "$ROOT/packaging/sudoers" "$STAGE/etc/sudoers.d/awg-panel"
chmod 440 "$STAGE/etc/sudoers.d/awg-panel"
cp "$ROOT/packaging/config.ini.example" "$STAGE/usr/share/awg-panel/config.ini.example"
# Ship a default conffile so dpkg tracks /etc/awg-panel/config.ini from v1;
# postinst still keeps existing user edits (conffile semantics).
cp "$ROOT/packaging/config.ini.example" "$STAGE/etc/awg-panel/config.ini"

# All files in .deb must be root-owned: dpkg-deb preserves staging uid/gid,
# and a sudoers file owned by uid 1001 breaks ALL sudo on target
# ("sudo: /etc/sudoers.d/awg-panel is owned by uid 1001, should be 0").
# chown covers root builds; --root-owner-group covers non-root builds (WSL/CI).
chown -R 0:0 "$STAGE" 2>/dev/null || true

if dpkg-deb --help 2>/dev/null | grep -q root-owner-group; then
  dpkg-deb --root-owner-group --build "$STAGE"
else
  dpkg-deb --build "$STAGE"
fi
echo "Built: $STAGE.deb"
