#!/usr/bin/env bash
#
# install_postgresql16_launchdaemon.sh
# -------------------------------------
# Migrate PostgreSQL 16 from user-level LaunchAgent (~/Library/LaunchAgents)
# to system-level LaunchDaemon (/Library/LaunchDaemons) so it starts at
# machine boot WITHOUT requiring a user to log into the GUI first.
#
# Usage (run in a LOCAL macOS Terminal, NOT inside a sandboxed IDE shell):
#   sudo bash /Users/xuchenfei/PycharmProjects/gangtise_demo/ops/install_postgresql16_launchdaemon.sh
#
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: this script must be run as root via sudo." >&2
  echo "       sudo bash $0" >&2
  exit 1
fi

TARGET_USER="${TARGET_USER:-xuchenfei}"
LABEL="com.local.postgresql16"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_PLIST="${PROJECT_DIR}/ops/com.local.postgresql16.plist"
DST_PLIST="/Library/LaunchDaemons/${LABEL}.plist"
OLD_AGENT_PLIST="/Users/${TARGET_USER}/Library/LaunchAgents/${LABEL}.plist"
TARGET_UID="$(id -u "$TARGET_USER")"

echo "[1/6] Source plist: ${SRC_PLIST}"
[ -f "$SRC_PLIST" ] || { echo "MISSING: $SRC_PLIST"; exit 2; }
plutil -lint "$SRC_PLIST" >/dev/null
echo "      plutil -lint: OK"

echo "[2/6] Install to ${DST_PLIST} (root:wheel mode=0644)"
cp -f "$SRC_PLIST" "$DST_PLIST"
chown root:wheel "$DST_PLIST"
chmod 0644 "$DST_PLIST"
ls -l "$DST_PLIST"

echo "[3/6] Retire user-level LaunchAgent (gui/${TARGET_UID})"
launchctl bootout "gui/${TARGET_UID}/${LABEL}" 2>&1 || true
if [ -f "$OLD_AGENT_PLIST" ]; then
  BACKUP="${OLD_AGENT_PLIST}.bakup_by_daemon_migration_$(date +%Y%m%d%H%M%S)"
  mv -f "$OLD_AGENT_PLIST" "$BACKUP"
  echo "      moved -> ${BACKUP}"
fi

echo "[4/6] Bootstrap LaunchDaemon into system domain"
launchctl bootstrap system "$DST_PLIST"

echo "[5/6] kickstart -kp to start PG right now (kill any stale, then print PID)"
launchctl kickstart -k -p "system/${LABEL}"

echo "[6/6] Wait for 127.0.0.1:5432 to accept connections (max 30s)"
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if /opt/homebrew/bin/pg_isready -h 127.0.0.1 -p 5432 -q; then
    echo "      PostgreSQL READY on 127.0.0.1:5432 after ${i}*2s"
    break
  fi
  echo "      poll ${i} ..."
  sleep 2
  if [ "$i" -eq 15 ]; then
    echo "TIMEOUT waiting for PostgreSQL. Diagnose: launchctl print system/${LABEL}" >&2
    exit 3
  fi
done

echo ""
echo "=== Summary ==="
echo "  - LaunchDaemon installed:  ${DST_PLIST}"
echo "  - RunAs user:              ${TARGET_USER} (UserName in plist)"
echo "  - Auto-start at boot:      YES (RunAtLoad=true, system scope, no GUI login needed)"
echo "  - Respawn on crash:        YES (KeepAlive=true)"
echo "  - Verify live status:"
echo "      launchctl print system/${LABEL}"
echo "      /opt/homebrew/bin/pg_isready -h 127.0.0.1 -p 5432"
