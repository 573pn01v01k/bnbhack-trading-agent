#!/usr/bin/env bash
# install_cron.sh — install/remove the 4-hourly decision cron for this host.
#
#   ./scripts/deploy/install_cron.sh           # install dry-run cron (safe)
#   LIVE=1 ./scripts/deploy/install_cron.sh     # install live cron (still date-gated to Jun 22–28 UTC)
#   ./scripts/deploy/install_cron.sh --remove   # remove it
#
# Runs at minute 1 of every 4th hour, UTC. run_cycle.sh enforces the contest-window
# gate, so an early/late firing can never trade live outside Jun 22–28.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TAG="# bnbhack-track1-agent"
RUNNER="$REPO/scripts/deploy/run_cycle.sh"
LIVE="${LIVE:-0}"
LINE="1 */4 * * * LIVE=$LIVE $RUNNER >> $REPO/logs/cron.log 2>&1 $TAG"

current="$(crontab -l 2>/dev/null || true)"
cleaned="$(printf '%s\n' "$current" | grep -v -F "$TAG" || true)"

if [ "${1:-}" = "--remove" ]; then
  printf '%s\n' "$cleaned" | crontab -
  echo "removed bnbhack cron."
  exit 0
fi

chmod +x "$RUNNER"
{ [ -n "$cleaned" ] && printf '%s\n' "$cleaned"; printf '%s\n' "$LINE"; } | crontab -
echo "installed (LIVE=$LIVE):"
echo "  $LINE"
echo
echo "NOTE: cron uses UTC and a bare PATH; run_cycle.sh adds the nvm/twak PATH and loads .env itself."
echo "Verify with: crontab -l | grep bnbhack"
