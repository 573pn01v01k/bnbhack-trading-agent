# BNB Hack — Autonomous Self-Custody Trading Agent (Track 1)

Submission for **BNB Hack: AI Trading Agent Edition** (BNB Chain × CoinMarketCap × Trust Wallet).
Target: **Track 1 — Autonomous Trading Agents** + the **Best Use of Trust Wallet Agent Kit** special.

A self-custodial autonomous agent that trades live on BSC over the Jun 22–28 window. Its market-read
brain runs on a crypto data layer most teams won't have — **Monolit** live on-chain BSC flow + CEX
derivatives, layered on **CoinMarketCap's Agent Hub** — it decides allocation under hard risk rules,
and signs/executes every trade itself through the **Trust Wallet Agent Kit** in unattended
self-custody mode. It pays for its data keyless, per request, via **x402**.

> Full design: [`docs/superpowers/specs/2026-06-16-bnbhack-trading-agent-design.md`](docs/superpowers/specs/2026-06-16-bnbhack-trading-agent-design.md)

## Result (full report in `docs/BACKTEST_RESULTS_TRACK1.md`)

Validated on **120 days of real hourly data** across **64 eligible BEP-20 tokens**, with a locked 21-day holdout never used to build the strategy.

| Strategy (live config) | Return | Sharpe | Max DD |
|---|---:|---:|---:|
| **Ensemble (convex) — full window** | **+20.0%** | 1.35 | 18.5% |
| Ensemble — locked 21d holdout | +3.5% | 3.14 | 4.8% |
| Equal-weight baseline | +13.7% | 0.91 | — |
| BTC buy-and-hold | −2.4% | — | 28% |

The live strategy is a **convex model-averaged ensemble**: regime-gated equal-weight over concentrated basket sizes (N=2/3 most-liquid, per-name cap 0.50) × regime MAs (240/336/480h), rebalanced every 4h. Model-averaging is anti-overfitting (never bets on one in-sample-best parameter); the concentration is **convex sizing** tuned for the single-week contest — it ~5×'s the weekly right tail (P(week>15%) 2%→~10% on overlapping windows; a 6–7% shot at a >20% week) while keeping worst-week and full-window drawdown **under the 30% DQ gate** (15.7% / 18.5–25.6%). Cost-robust to 40 bps.

**Honest caveats** (from full robustness validation): returns are **strongly regime-dependent and the fat tail is episodic** — sub-periods run −12% / +40% / −2%, almost all upside comes from one trending stretch, and on the *independent* (non-overlapping) 7-day sample the realized max was ~14% with P(>15%)=0%. So the headline tail is real *optionality* for a trending week, not a per-week promise; in a choppy/down week the book bleeds modestly with downside gated, never a blow-up. This is amplified regime-beta + a capped moonshot, **not** stable selection alpha — ~15 signal hypotheses (momentum, flow, whale-copy, funding, news-tilt, depeg, unlock, listing, squeeze, DEX/CEX lead-lag, LLM-allocator) were tested across three multi-agent rounds and **all rejected** as return-alpha; convex sizing + bounded risk-control overlays are what survived. Reproduce: `python3 -m bnbhack_agent.cli track1-backtest`.

## How it works

- **Strategy** (`strategy.py`): the robust model-averaged ensemble above. Hold the basket when BTC is risk-on (above its regime MA), rotate to the stablecoin leg otherwise. The same function drives backtest and live (decision parity).
- **Data layer + partner signals**: live **Monolit** MCP (`monolit.py`) — on-chain BSC flow, CEX derivatives/funding, token security; **CMC Agent Hub** (`cmc.py`) — Fear & Greed / dominance euphoria guard; **MiniMax M3 via 0G** (`news_veto.py`) — a **negative-news veto** that drops a held token on a fresh severe event (hack/exploit/depeg/delisting), validated on the STG −64% Coinbase-delisting crash. All three are **bounded, logged, best-effort overlays** off the hot path that never block the core decision.
- **Signal research** (`docs/hypotheses/`, `scripts/research*.py`): ~15 hypotheses tested across two multi-agent rounds (momentum, flow, whale-copy, funding, news-tilt, stablecoin depeg, unlock-fade, listing pumps, funding squeeze) — all rejected as return-alpha under walk-forward + locked holdout + TWAK cost. Honest conclusion: the edge is regime-gated beta + a capped moonshot lottery; the partner signals add **risk control**, not fabricated alpha. See `docs/hypotheses/SUMMARY.md`.
- **Engine** (`marketdata.py`, `portfolio.py`, `walkforward.py`, `scripts/research.py`, `scripts/robustness.py`): cached price panels, no-lookahead simulator, walk-forward OOS + locked-holdout evaluation, and an auto-research ledger that records every hypothesis tested (the multiple-comparison budget).
- **Execution** (`execution.py`): Trust Wallet Agent Kit in self-custody — `twak swap --chain bsc`, x402-paid data, `serve --watch` for unattended signing. Risk caps gate every trade (drawdown stop inside the 30% gate, per-trade/daily limits, slippage).
- **Agent** (`agent.py`): 4-hourly decision (~74s) → risk-gated trade plan → self-custody execution → structured decision log. Edge degrades gracefully (best-effort, never blocks).
- **Registration** (`register.py`): the BSC `CompetitionRegistry` (optional `web3` extra).

`cmc_skill.py` (a Track‑2 Strategy Skill exporter) is carried over but is not part of this Track‑1 submission. Tests: **70 passing**.

## Usage

```bash
python3 -m pip install -e .                 # optionally: pip install 'web3>=6'  (on-chain registration)
python3 -m pytest -q                         # 70 passed
PYTHONPATH=src python3 -m bnbhack_agent.cli track1-backtest          # reproduce the OOS result
PYTHONPATH=src python3 -m bnbhack_agent.cli track1-run               # one decision cycle (dry-run)
MONOLIT_API_KEY=... PYTHONPATH=src python3 -m bnbhack_agent.cli track1-run --monolit  # with the live edge
PYTHONPATH=src python3 -m bnbhack_agent.cli track1-register          # registration window/status
```

## The contest, briefly

149 eligible BEP-20 tokens; portfolio valued in USD hour-by-hour; ranked by **% return** with simulated
costs; **30% max-drawdown = disqualification**; ≥1 trade/day. Registration on the BSC `CompetitionRegistry`
`0x212c61b9b72c95d95bf29cf032f5e5635629aed5` before the Jun 22 trading window. See `docs/HACKATHON_RULES.md`.

## Quickstart (baseline engine)

```bash
python3 -m pip install -e .
python3 -m pytest -q
PYTHONPATH=src python3 -m bnbhack_agent.cli battle --source binance --symbols BNB --count 1000 --out runs/battle_bnb --train-ratio 0.70
```

## Disclaimer

Research and live-trading software. Not financial advice. Trades on-chain with real funds and can lose money.
