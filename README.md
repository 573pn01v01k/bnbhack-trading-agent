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

Validated on **120 days of real hourly data**, net of **measured per-name PancakeSwap slippage** (the agent executes on a DEX, so this is the cost that matters), with a locked 21-day holdout never used to build the strategy.

| Strategy (live config) | Return | Sharpe | Max DD |
|---|---:|---:|---:|
| **DEX-liquid blended book — full window (realistic cost)** | **+4.3%** | 0.51 | **15.9%** |
| DEX-liquid blended book — locked 21d holdout | **+1.7%** | 1.19 | 7.0% |
| _(reference) same book @ optimistic 10 bps_ | +17.4% | — | — |
| Equal-weight (DEX-liquid set) baseline | +13.5% | 0.95 | 29.6% |
| BTC buy-and-hold | −2.9% | — | 28.0% |

> **A red-team audit changed this result, and we kept the honest version.** An earlier draft ranked the basket by *Binance CEX* volume and assumed a flat 10 bps cost — reporting ~**+20%**. But the agent trades on **PancakeSwap**, not Binance. Re-measuring on-chain depth showed that book concentrated into names with almost no DEX liquidity and would have hit **50%+ drawdown from real slippage → automatic disqualification**. The fix: rank and restrict the investable set to names with real BSC DEX depth (> $20k/wk) — **{ASTER, CAKE, ZEC, XRP, DOGE}** — and price slippage per name. The honest book is **DQ-safe (18.7% < 30% gate) with a modest right tail**, not a +20% edge. The red-team reports are in [`docs/redteam/`](docs/redteam/).

The live strategy **blends two sleeves**: (1) a regime-gated **model-averaged ensemble** — equal-weight over basket sizes N=3/4 of the DEX-liquid set (per-name cap 0.34) × regime MAs (240/336/480h) — and (2) a **30% always-invested core EW sleeve** that captures the beta the binary gate sits out and keeps the book trading every bar (so the ≥1-trade/day rule is organic). Two circuit-breakers protect both: a **regime-hysteresis** gate (exit risk-off fast, re-enter only above MA×1.0075) and a **20% per-name trailing stop**. The **core fraction is a smooth, monotonic risk dial** validated DQ-safe across its range (0.0 pure-gate: −2.2%/DD18.7%; 0.30 default: +4.3%/DD15.9%; 0.50: +8.5%/DD18.2%) — 0.30 earns *higher* return **and** *lower* drawdown than the pure gate because the two sleeves' drawdowns offset. Model-averaging is anti-overfit; N=(3,4) over the 4 deepest names is the validated sweet spot (a full 59-token on-chain scan rejected expanding the universe: N=(4,5) −6.0%, N=5 −8.4%).

**Honest conclusion.** Net of realistic DEX slippage, **no positive return-alpha survives in this universe** — consistent with the ~15 signal hypotheses (momentum, flow, whale-copy, funding, news-tilt, depeg, unlock, listing, squeeze, DEX/CEX lead-lag, LLM-allocator) tested across multi-agent rounds and **all rejected**. Returns are regime-dependent (sub-periods −15.9% / +19.8% / −2.9%); the right tail is real *optionality* (max 7-day +22.7%, P(week>15%)=4%) but not a per-week promise. The leaderboard play is therefore **convexity + not getting disqualified**: a book that can post a >15% trending week while its drawdown stays well inside the 30% gate, plus bounded risk-control overlays (F&G guard, security veto, negative-news veto). The optional moonshot sleeve was tested and **defaults off** — it is a ~−1.9pp drag once slippage is real. Reproduce: `python3 -m bnbhack_agent.cli track1-backtest`.

## How it works

- **Strategy** (`strategy.py`): the blended book above, over the **DEX-liquid set only** (`universe.dex_liquid_candidates` — ranked by measured on-chain depth, not CEX volume). The regime-gated ensemble rotates to the stablecoin leg when BTC is risk-off; the 30% always-invested core stays (trailing-stopped). A per-name trailing stop drops any held name that craters. The same `combined_weights` function drives backtest and live (decision parity).
- **Data layer + partner signals**: live **Monolit** MCP (`monolit.py`) — on-chain BSC flow, CEX derivatives/funding, token security; **CMC Agent Hub** (`cmc.py`) — Fear & Greed / dominance euphoria guard; **MiniMax M3 via 0G** (`news_veto.py`) — a **negative-news veto** that drops a held token on a fresh severe event (hack/exploit/depeg/delisting), validated on the STG −64% Coinbase-delisting crash. All three are **bounded, logged, best-effort overlays** off the hot path that never block the core decision.
- **Signal research** (`docs/hypotheses/`, `scripts/research*.py`): ~15 hypotheses tested across two multi-agent rounds (momentum, flow, whale-copy, funding, news-tilt, stablecoin depeg, unlock-fade, listing pumps, funding squeeze) — all rejected as return-alpha under walk-forward + locked holdout + TWAK cost. Honest conclusion: the edge is regime-gated beta + a capped moonshot lottery; the partner signals add **risk control**, not fabricated alpha. See `docs/hypotheses/SUMMARY.md`.
- **Engine** (`marketdata.py`, `portfolio.py`, `walkforward.py`, `scripts/research.py`, `scripts/robustness.py`): cached price panels, no-lookahead simulator, walk-forward OOS + locked-holdout evaluation, and an auto-research ledger that records every hypothesis tested (the multiple-comparison budget).
- **Execution** (`execution.py`): Trust Wallet Agent Kit in self-custody — `twak swap --chain bsc`, x402-paid data, `serve --watch` for unattended signing. Risk caps gate every trade (drawdown stop inside the 30% gate, per-trade/daily limits, slippage).
- **Agent** (`agent.py`): 4-hourly decision (~74s) → risk-gated trade plan → self-custody execution → structured decision log. Edge degrades gracefully (best-effort, never blocks).
- **Registration** (`register.py`): the BSC `CompetitionRegistry` (optional `web3` extra).

`cmc_skill.py` (a Track‑2 Strategy Skill exporter) is carried over but is not part of this Track‑1 submission. Tests: **77 passing**.

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
