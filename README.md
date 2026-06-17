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
| **Ensemble — full window** | **+9.0%** | 0.83 | 16.4% |
| Ensemble — locked 21d holdout | +3.5% | 3.71 | 3.2% |
| Equal-weight baseline | −0.7% | 0.26 | — |
| BTC buy-and-hold | −2.4% | — | 28% |

The live strategy is a **model-averaged ensemble**: regime-gated equal-weight over a grid of basket sizes (N=3/5/8 most-liquid) × regime MAs (240/336/480h), rebalanced every 4h. Model-averaging is anti-overfitting by construction — it never bets on one in-sample-best parameter — and it's the only high-return config that also survives the holdout. **Cost-robust to ~20 bps** (+5.8% at 20bps; the 4h rebalance halves turnover vs hourly).

**Honest caveats** (from full robustness validation): returns are **regime-dependent** (−10% / +20% / +0% across three sub-periods) — this is diversified crypto-beta capture with a downside regime gate, *not* a stable systematic edge. Naive momentum, reversal, vol-concentration, time-series momentum, adaptive sizing, and on-chain DEX-flow selection were all tested under the same walk-forward + holdout protocol and **rejected**; the ensemble is what survived. Reproduce: `python3 -m bnbhack_agent.cli track1-backtest`.

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
