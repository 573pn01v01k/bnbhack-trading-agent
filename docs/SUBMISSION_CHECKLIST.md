# Submission Checklist — BNB Hack Track 1

The systematic build is **functionally complete**: validated cost-robust ensemble strategy, fast
self-custody agent (~74s/decision), honest backtest report, auto-research + robustness harnesses,
70 tests passing, all pushed. What remains needs a human + on-chain actions (cannot be automated here).

## Two deadlines (don't conflate them)
- **DoraHacks form submission — Jun 21 · 12:00 UTC** (the binding "you're in the competition" gate). Verified live on DoraHacks 2026-06-20.
- **On-chain registration — contract open until Jun 25 · 00:00 UTC** (read live from the registry); register before the **Jun 22** trading-window open. Trading runs Jun 22–28.

## Done (in repo)
- [x] Strategy: blended book (regime-gated ensemble + 30% core, 4h rebalance), walk-forward + holdout validated, cost-robust net of measured per-name DEX slippage.
- [x] Live agent: decision → risk-gated trade plan → TWAK self-custody execution → decision log; Monolit edge cached/best-effort.
- [x] Backtest report + **7 charts** (`docs/assets/`, regen `scripts/make_charts.py`), design spec, research log + ledger.
- [x] Execution (`twak swap --chain bsc`, x402, serve) and registration code (`register.py`; or the official `twak compete register`).
- [x] **77 tests; repo pushed and PUBLIC.**
- [x] **TWAK CLI 0.19.1 installed on this host** (nvm Node 22 at `~/.nvm/versions/node/v22.23.0/bin`); `twak compete` confirmed present.
- [x] **Deploy harness on this machine**: `scripts/deploy/run_cycle.sh` (4h cycle, contest-window-gated live, JSONL decision log) + `scripts/deploy/install_cron.sh`. Dry-run cycle verified end-to-end.
- [x] **Submission writeup** drafted: `docs/SUBMISSION_WRITEUP.md`. **Demo storyboard**: `docs/DEMO_SCRIPT.md`.

## Remaining — needs Pavel
1. **Trust Wallet Developer Portal credentials** (NEW — any networked `twak` command needs them): `TWAK_ACCESS_ID` + `TWAK_HMAC_SECRET` from the portal, into the gitignored `.env`.
2. **Agent wallet** — cleanest path is to let **TWAK create it** (`twak wallet` / `twak setup`); the key stays encrypted under `TWAK_WALLET_PASSWORD` and is never pasted anywhere. (Importing an existing `AGENT_PRIVATE_KEY` is the fallback.)
3. **Fund that wallet** (low stakes): ≤$500 USDT/USDC on **BSC** (trading), a little USDC on **Base** (x402), some **BNB** (gas).
4. **Register** before Jun 22: `twak compete register` (official; scores for Best Use of TWAK), verify `twak compete status`. Fallback: `track1-register` + `register.register_agent(dry_run=False)` via the `/tmp/w3venv` web3.
5. **Submit the DoraHacks form by Jun 21 12:00 UTC**: public repo URL (done), agent wallet address, the `SUBMISSION_WRITEUP.md` copy, Telegram contact.
6. **Go live**: `LIVE=1 ./scripts/deploy/install_cron.sh` for Jun 22–28 (the runner self-gates to the window). Dry-run first.
7. **Record the demo** per `docs/DEMO_SCRIPT.md` — on-chain tx hashes (register + a self-custody swap) + the x402 payment.

## Honest expectation
This is a robust, non-blow-up, regime-gated diversified-beta agent with a deep self-custody/x402
integration — strong for the **Best Use of TWAK** craft prize and a respectable PnL finish in a
risk-on week. It is not a guaranteed leaderboard #1: a 7-day PnL contest is won by the right tail
(concentration + luck), and we deliberately optimized for "don't blow up" + craft over a lottery bet.
