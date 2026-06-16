# BNB Hack — Autonomous Self-Custody Trading Agent (Track 1)

Submission for **BNB Hack: AI Trading Agent Edition** (BNB Chain × CoinMarketCap × Trust Wallet).
Target: **Track 1 — Autonomous Trading Agents** + the **Best Use of Trust Wallet Agent Kit** special.

A self-custodial autonomous agent that trades live on BSC over the Jun 22–28 window. Its market-read
brain runs on a crypto data layer most teams won't have — **Monolit** live on-chain BSC flow + CEX
derivatives, layered on **CoinMarketCap's Agent Hub** — it decides allocation under hard risk rules,
and signs/executes every trade itself through the **Trust Wallet Agent Kit** in unattended
self-custody mode. It pays for its data keyless, per request, via **x402**.

> Full design: [`docs/superpowers/specs/2026-06-16-bnbhack-trading-agent-design.md`](docs/superpowers/specs/2026-06-16-bnbhack-trading-agent-design.md)

## Status

This repo starts from a working backtest/strategy baseline and is being built into the live Track‑1 agent.

**Reused as-is (verified working, 15 tests passing):**
- `indicators.py` — SMA/EMA/Wilder-RSI/MACD/rolling-std.
- `backtest.py` — deterministic, no-lookahead, fee/drawdown/Sharpe model (supports shorts).
- `battle.py` — train/test split + grid search; scoring already weights held-out profit first with a >30% drawdown penalty (matches Track 1).
- `models.py`, `research_loop.py` (propose→backtest→critique→mutate scaffold), `execution.py` (TWAK CLI adapter).

**Being rebuilt for Track 1:**
- **Real Monolit integration.** The baseline `MonolitMCPEnrichmentSource` is a placeholder that calls a non-existent tool and returns nothing — it is replaced with real Monolit MCP calls (`query_evm_onchain` on-chain BSC flow, `query_cex_normalized` funding/OI/taker, `get_token_security`, etc.).
- **Multi-token rotation.** Baseline strategies are single-asset daily TA; the live engine rotates across the fixed 149 eligible BEP-20 tokens (+ stables) on an hourly cadence.
- **Full execution.** Quote-only → real swaps, plus `x402` data payments, `automate` cadence, and `serve --watch` for unattended autonomous signing.

`cmc_skill.py` (a Track‑2 Strategy Skill exporter) is carried over but is not part of the Track‑1 submission.

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
