# Track-1 Backtest Results — live strategy (DEX-liquid ensemble)

Window: 2880 bars, 2026-02-16 16:00:00+00:00 → 2026-06-16 15:00:00+00:00. Investable set (ranked by **measured BSC DEX volume**, > $20k/wk): **ZEC, CAKE, ASTER, XRP, ADA, STG, DOGE** (7 names). The agent executes spot on PancakeSwap via TWAK, so the universe is filtered by on-chain depth, **not** Binance/CEX volume.

Live config: model-averaged ensemble of regime-gated equal-weight over basket sizes N=[3, 4] × regime MAs=[240, 336, 480], per-name cap 0.34, regime **hysteresis** band 0.0075, per-name **20% trailing stop**, rebalanced every 4h. Cost model: **measured per-name BSC DEX slippage + 25bps LP fee**.

> **Why this report differs from earlier drafts.** Earlier versions ranked by CEX volume and assumed a flat 10 bps cost, reporting ~+20%. A red-team audit showed that book concentrated into names with ~no on-chain depth and would have hit **50%+ drawdown from real DEX slippage → automatic disqualification**. The headline below is now net of **measured per-name PancakeSwap slippage**, on the DEX-liquid set only. The honest result is a **DQ-safe book with a modest right tail**, not a +20% edge.

## Headline (net of realistic per-name DEX slippage)

| | Return | Sharpe | Max DD |
|---|---:|---:|---:|
| **Live book, full window (realistic cost)** | **-2.2%** | **0.04** | **18.7%** |
| Live book, locked 21d holdout | +3.1% | 3.65 | 2.5% |
| _(reference) same book @ optimistic 10bps_ | +15.2% | 1.26 | 14.4% |
| Equal-weight (DEX-liquid set) baseline | +13.9% | 0.96 | 28.7% |
| BTC buy-and-hold | -2.9% | 0.01 | 28.0% |

**Max drawdown 18.7% is inside the 30% disqualification gate** — the design priority. The per-name trailing stop and regime hysteresis are what hold it there.

## Cost sensitivity

| tx cost | full-window return |
|---:|---:|
| 0 bps | +17.8% |
| 10 bps | +15.2% |
| 40 bps | +7.8% |
| 80 bps | -1.3% |
| per-name (live) | -2.2% |

The gap between the 10 bps line and the per-name line is exactly the cost the earlier report hid. Honest numbers, not the flattering ones.

## Honest caveats — robustness validation

- **Returns are regime-dependent, not a stable edge.** Across three equal sub-periods: -15.9%, +19.8%, -2.9%. This is diversified crypto-beta capture with a downside regime gate + circuit-breakers — not systematic alpha.
- **7-day right tail** (leaderboard relevance): mean +0.1%, p95 +12.2%, max +22.7%, P(week > 15%) 4.0%.
- ~15 signal hypotheses (momentum, flow, whale-copy, funding, news-tilt, depeg, unlock, listing, squeeze, DEX/CEX lead-lag, LLM-allocator) were tested under walk-forward + locked holdout + cost and **rejected** as return-alpha. What survived: regime-gated DEX-liquid beta + bounded risk-control overlays (F&G guard, security veto, negative-news veto). The leaderboard play is convexity + not getting disqualified.

Reproduce: `python3 -m bnbhack_agent.cli track1-backtest`.
