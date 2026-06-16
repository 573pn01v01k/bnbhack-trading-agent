# Track-1 Build Plan

Spec: `docs/superpowers/specs/2026-06-16-bnbhack-trading-agent-design.md`. Spot-only MVP, ≤$500, craft-first.
Anti-overfitting and empirical confirmation are hard requirements (per goal).

## Confirmed foundations (real data, 2026-06-16)
- Monolit runtime MCP: `https://mcp.monolit.network/mcp` (header `X-Api-Key`, billing unlim-pipeline). Key via env, never committed.
- On-chain BSC `evm.defi_events`: live, 9.6M rows/24h, fresh to the minute → the signal moat.
- Price for backtest: public Binance hourly klines (reliable) for liquid subset; on-chain for long tail.
- Differentiation: competitor field (91 BUIDLs) is mostly Track-2 CMC skills; closest Track-1 rival is Formion (CMC-only). Our wedge = Monolit on-chain flow + CEX derivatives nobody else has.

## Modules (src/bnbhack_agent/)
1. `monolit.py` — real MCP streamable-HTTP client (initialize→tools/call, SSE parse). Typed helpers: onchain_flow, cex_funding, cex_taker, ta. **Replaces the fake MonolitMCPEnrichmentSource.** [live-test required]
2. `universe.py` — the ~147 eligible tokens → resolve {symbol, bsc_contract, binance_pair}; classify liquid vs long-tail.
3. `data_sources.py` — extend: hourly multi-symbol Binance klines; on-chain price fallback. Keep CMC/fixture.
4. `signals.py` — per-token features: momentum, on-chain net-inflow (defi_events), CEX taker-skew, funding-regime, TA. Historical (backtest) + latest (live) parity.
5. `portfolio.py` — multi-asset hourly portfolio backtest on top of the verified `backtest.py` primitives: scores→weights (caps, stables fallback, regime gate)→equity/DD/return/turnover w/ simulated costs.
6. `walkforward.py` — **anti-overfit core**: rolling train/test, param search on train only, OOS evaluation, aggregate OOS metrics + baseline (equal-weight / BNB B&H) comparison, honest in/out spread report. No single-window cherry-pick.
7. `execution.py` — extend TWAK adapter: real swap, x402 request, automate cadence, serve. + risk caps.
8. `register.py` — CompetitionRegistry.register() via web3 signer.
9. `agent.py` — live autonomous loop (signals→decide→execute→log) with risk gates; cron/`serve --watch` friendly.
10. `cli.py` — commands: resolve-universe, fetch-data, signals, walkforward, register, run, dry-run.

## Build order (each step confirmed before moving on)
1. monolit.py + live smoke test. ← now
2. universe resolution + coverage report (how many of 147 are tradeable).
3. signals + portfolio backtest + walkforward → **confirmed OOS metrics vs baseline** (the headline result).
4. execution + register + agent loop (unit-tested; dry-run; no live funds yet).
5. tests green, docs, commit, flip public before Jun 21.

## Anti-overfitting rules
- Param selection on train windows only; report held-out OOS.
- Multiple rolling windows; report distribution, not best single window.
- Always compare to equal-weight and BNB buy-and-hold baselines.
- Penalize turnover + simulated costs; respect the 30% DD gate as a hard constraint.
- Prefer few robust parameters over many; flag any config that only wins one window.
