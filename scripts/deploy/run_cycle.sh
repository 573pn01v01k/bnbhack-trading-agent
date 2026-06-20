#!/usr/bin/env bash
# run_cycle.sh — one autonomous decision cycle for the BNB Hack Track-1 agent.
# Designed to be driven by cron every 4h on this host. Dry-run by default; trades
# live ONLY when LIVE=1 *and* the current UTC date is inside the contest window.
#
#   LIVE=0  ./scripts/deploy/run_cycle.sh     # dry-run (safe; default)
#   LIVE=1  ./scripts/deploy/run_cycle.sh     # live, but still gated to Jun 22–28 UTC
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

# --- environment ---------------------------------------------------------------
# nvm Node 22 carries the `twak` binary; cron has a bare PATH, so add it explicitly.
NVM_NODE_BIN="$HOME/.nvm/versions/node/v22.23.0/bin"
[ -d "$NVM_NODE_BIN" ] && export PATH="$NVM_NODE_BIN:$PATH"
export PYTHONPATH="$REPO/src"

# Secrets live in the gitignored .env (CMC_PRO_API_KEY, TWAK_ACCESS_ID,
# TWAK_HMAC_SECRET, TWAK_WALLET_PASSWORD, MONOLIT_API_KEY, ...).
if [ -f "$REPO/.env" ]; then
  set -a; . "$REPO/.env"; set +a
fi

LOG_DIR="$REPO/logs"; mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
LOG="$LOG_DIR/decisions.jsonl"

# --- contest-window gate -------------------------------------------------------
# Live trades only inside [2026-06-22, 2026-06-28] UTC. Outside the window we still
# run (to keep state warm / prove the loop) but force dry-run.
TODAY="$(date -u +%Y%m%d)"
WINDOW_START=20260622
WINDOW_END=20260628
MODE="dry-run"
LIVE_FLAG=""
if [ "${LIVE:-0}" = "1" ] && [ "$TODAY" -ge "$WINDOW_START" ] && [ "$TODAY" -le "$WINDOW_END" ]; then
  MODE="LIVE"; LIVE_FLAG="--live"
fi

# --- monolit edge (only if key present) ----------------------------------------
MONOLIT_FLAG=""
[ -n "${MONOLIT_API_KEY:-}" ] && MONOLIT_FLAG="--monolit"

echo "[$STAMP] cycle start — mode=$MODE monolit=${MONOLIT_FLAG:-off}" >&2

# --- run -----------------------------------------------------------------------
set +e
OUT="$(python3 -m bnbhack_agent.cli track1-run $LIVE_FLAG $MONOLIT_FLAG 2>&1)"
RC=$?
set -e

# Persist a one-line audit record per cycle.
printf '{"ts":"%s","mode":"%s","rc":%d,"out":%s}\n' \
  "$STAMP" "$MODE" "$RC" "$(printf '%s' "$OUT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')" \
  >> "$LOG"

echo "$OUT" >&2
echo "[$STAMP] cycle end — rc=$RC (logged to $LOG)" >&2
exit $RC
