# Submission Checklist — BNB Hack Track 1

The systematic build is **functionally complete**: validated cost-robust ensemble strategy, fast
self-custody agent (~74s/decision), honest backtest report, auto-research + robustness harnesses,
70 tests passing, all pushed. What remains needs a human + on-chain actions (cannot be automated here).

## Done (in repo)
- [x] Strategy: model-averaged ensemble (regime-gated EW over N×MA, 4h rebalance), walk-forward + holdout validated, cost-robust to ~20bps.
- [x] Live agent: decision → risk-gated trade plan → TWAK self-custody execution → decision log; Monolit edge cached/best-effort.
- [x] Backtest report (`docs/BACKTEST_RESULTS_TRACK1.md`), design spec, research log + ledger.
- [x] Execution (`twak swap --chain bsc`, x402, serve) and on-chain registration code (`register.py`).
- [x] 70 tests; repo pushed (private).

## Remaining — needs Pavel
1. **Fund the agent wallet** (low stakes by design): ≤$500 in a BSC stablecoin (USDT/USDC) for trading, a little USDC on **Base** for x402 data payments, and some **BNB** for gas.
2. **Configure secrets** (never commit): `AGENT_PRIVATE_KEY`, `BSC_RPC_URL`, `TWAK_WALLET_PASSWORD`, `MONOLIT_API_KEY`, optionally `CMC_PRO_API_KEY`. `pip install 'web3>=6'` for registration.
3. **Register on-chain BEFORE Jun 22** (trading window opens) on `CompetitionRegistry 0x212c61b9b72c95d95bf29cf032f5e5635629aed5`: `register.register_agent(dry_run=False)`; verify `track1-register`.
4. **Deploy** to the always-on VPS; run the agent on a **4h cron** (or `twak serve --watch`) for Jun 22–28. Dry-run first (`track1-run`), then `--live`.
5. **DoraHacks submission**: submit the public repo URL + agent wallet address + a short strategy writeup; answer the form (Telegram contact, agent address). **Flip the repo public** before submitting.
6. **Demo**: short video showing the autonomous self-custody loop end-to-end with on-chain proof (BSC tx hashes) + the x402 data payment — this is what the *Best Use of TWAK* panel scores.

## Honest expectation
This is a robust, non-blow-up, regime-gated diversified-beta agent with a deep self-custody/x402
integration — strong for the **Best Use of TWAK** craft prize and a respectable PnL finish in a
risk-on week. It is not a guaranteed leaderboard #1: a 7-day PnL contest is won by the right tail
(concentration + luck), and we deliberately optimized for "don't blow up" + craft over a lottery bet.
