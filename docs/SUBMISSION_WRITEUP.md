# DoraHacks Submission — Autonomous Self-Custody Trading Agent (Track 1)

*Paste-ready copy for the DoraHacks form. Sections map to the usual fields; trim per the form's limits.*

---

## Tagline (one line)

A self-custodial AI agent that reads the market on a deep on-chain data layer, sizes its book under hard risk rules, and signs every BSC swap itself through the Trust Wallet Agent Kit.

## Tracks

Track 1 — Autonomous Trading Agents. Also competing for **Best Use of the Trust Wallet Agent Kit**.

## The problem

A 7-day live-PnL contest with a **30% max-drawdown disqualification** is not won by the boldest bet — it's won by the book that captures a trending week *without blowing up*. Most agents over-fit a signal on backtest, then get disqualified on real DEX slippage. We built the opposite: an honest, risk-first agent whose edge is **convexity + survival**.

## How it works

A 4-hour decision loop, fully autonomous and self-custodial:

1. **Read regime** from a data layer most teams won't have — **Monolit** live on-chain BSC flow + CEX derivatives, layered on **CoinMarketCap's Agent Hub** (Fear & Greed, dominance), with a **MiniMax M3** negative-news veto.
2. **Size a two-sleeve book** (`combined_weights`, the same function in backtest and live — decision parity):
   - a **regime-gated model-averaged ensemble** (equal-weight over basket sizes N=3/4 of the DEX-liquid set × three regime MAs 240/336/480h) that rotates to stables when BTC is risk-off;
   - a **30% always-invested core** that captures the beta the gate sits out and keeps the book trading every bar (so the ≥1-trade/day rule is organic).
3. **Protect it** with two circuit-breakers: regime hysteresis (re-enter only above MA×1.0075) and a **20% per-name trailing stop**.
4. **Execute in self-custody** via the **Trust Wallet Agent Kit** — `twak swap --chain bsc`, the agent signs every trade itself, pays for data keyless per-request via **x402**, and registers on-chain with `twak compete register`.

## Sponsor stack (all three)

- **CoinMarketCap** — signal layer (Agent Hub: Fear & Greed, dominance, market data).
- **Trust Wallet Agent Kit** — execution layer (self-custody signing, `compete` registration, x402 micropayments).
- **BNB Chain** — venue (spot swaps on PancakeSwap; universe ranked by measured BSC DEX depth).

## Results — honest, validated

Validated on **120 days of real hourly data**, net of **measured per-name PancakeSwap slippage**, with a **locked 21-day holdout** never used to build the strategy:

| | Return | Sharpe | Max DD |
|---|---:|---:|---:|
| **Blended book — full window (realistic cost)** | **+4.3%** | 0.51 | **15.9%** |
| Blended book — locked 21d holdout | +1.7% | 1.19 | 7.0% |

Across 17 non-overlapping weeks, **zero** breached the 30% gate. Worst drawdown over the whole window: 15.9% — wide headroom.

**What makes this submission credible:** a red-team audit caught an earlier draft that ranked by CEX volume + assumed flat 10bps cost and reported ~+20%. We re-measured on-chain depth, found that book would have hit 50%+ drawdown on real slippage, and **kept the honest version** — DEX-depth-ranked universe, per-name slippage, ~15 signal hypotheses tested and rejected under walk-forward + holdout + cost. The reports are in `docs/redteam/`.

## What's novel

- **Decision parity** — one `combined_weights` function drives backtest and live, so the reported numbers are the deployed numbers.
- **A monotonic risk dial** (`core_ew_frac`) validated DQ-safe across its full range.
- **Self-custody + x402** depth: the agent holds its own keys via TWAK and pays for data per-request on-chain — no custodial exchange, no API-key data contracts.
- **Honesty as a feature** — we report the conservative cost floor and publish the red-team that changed our headline.

## Links

- Repo: https://github.com/573pn01v01k/bnbhack-trading-agent (public)
- Reproduce results: `PYTHONPATH=src python3 -m bnbhack_agent.cli track1-backtest`
- Charts: `docs/assets/` (regenerate with `scripts/make_charts.py`)
- Agent wallet address: **`<fill after wallet is created>`**
- Demo video: **`<fill after recording>`**
- Telegram contact: **`<fill>`**

## Honest expectation

A robust, non-blow-up, regime-gated diversified-beta agent with a deep self-custody/x402 integration. Strong for **Best Use of TWAK** and a respectable PnL finish in a risk-on week — built to survive the drawdown gate and catch the right tail, not to win a lottery.
