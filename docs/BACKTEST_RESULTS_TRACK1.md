# Track-1 Backtest Results — live strategy (DEX-liquid ensemble)

Window: 2880 bars, 2026-02-16 16:00:00+00:00 → 2026-06-16 15:00:00+00:00. Investable set (ranked by **measured BSC DEX volume**, > $20k/wk): **ZEC, CAKE, ASTER, XRP, ADA, STG, DOGE** (7 names). The agent executes spot on PancakeSwap via TWAK, so the universe is filtered by on-chain depth, **not** Binance/CEX volume.

Live config: a blend of (1) the regime-gated model-averaged ensemble over basket sizes N=[3, 4] × regime MAs=[240, 336, 480] and (2) a **30% always-invested core EW sleeve** (the risk dial — see below); per-name cap 0.34, regime **hysteresis** band 0.0075, per-name **20% trailing stop**, rebalanced every 4h. Cost model: **measured per-name BSC DEX slippage + 25bps LP fee**.

> **Why this report differs from earlier drafts.** Earlier versions ranked by CEX volume and assumed a flat 10 bps cost, reporting ~+20%. A red-team audit showed that book concentrated into names with ~no on-chain depth and would have hit **50%+ drawdown from real DEX slippage → automatic disqualification**. The headline below is now net of **measured per-name PancakeSwap slippage**, on the DEX-liquid set only. The honest result is a **DQ-safe book with a modest right tail**, not a +20% edge.

## Headline (net of realistic per-name DEX slippage)

| | Return | Sharpe | Max DD |
|---|---:|---:|---:|
| **Live book, full window (realistic cost)** | **+4.3%** | **0.51** | **15.9%** |
| Live book, locked 21d holdout | +1.7% | 1.19 | 7.0% |
| _(reference) same book @ optimistic 10bps_ | +17.4% | 1.36 | 14.3% |
| Equal-weight (DEX-liquid set) baseline | +13.5% | 0.94 | 29.6% |
| BTC buy-and-hold | -2.9% | 0.01 | 28.0% |

**Max drawdown 15.9% is inside the 30% disqualification gate** — the design priority. The per-name trailing stop and regime hysteresis are what hold it there.

## Risk dial — the core-exposure frontier

The book blends a regime-gated ensemble with a **30% always-invested core** (EW over the DEX-liquid top-4, protected only by the trailing stop). That core fraction is a smooth, monotonic risk dial, validated DQ-safe across its range:

| core EW frac | full return | full DD | holdout return | holdout DD |
|---:|---:|---:|---:|---:|
| 0.00 (pure gate, min risk) | −2.2% | 18.7% | +3.1% | 2.5% |
| **0.30 (shipped default)** | **+4.3%** | **15.9%** | **+1.7%** | **7.0%** |
| 0.50 (more upside) | +8.5% | 18.2% | +0.6% | 11.4% |

The default 0.30 is the conservative pick — it earns *higher* full return **and** *lower* full drawdown than the pure gate (the two sleeves' drawdowns offset), while the holdout stays positive and far inside the gate. The always-invested core also makes the contest's ≥1-trade/day requirement organic (no synthetic heartbeat needed). Dial up toward 0.50 for more upside in a trending week, at more drawdown.

## Cost sensitivity

| tx cost | full-window return |
|---:|---:|
| 0 bps | +19.3% |
| 10 bps | +17.4% |
| 40 bps | +11.9% |
| 80 bps | +5.0% |
| per-name (live) | +4.3% |

The gap between the 10 bps line and the per-name line is exactly the cost the earlier report hid. Honest numbers, not the flattering ones.

## Honest caveats — robustness validation

- **Returns are regime-dependent, not a stable edge.** Across three equal sub-periods: -13.7%, +23.5%, -2.1%. This is diversified crypto-beta capture with a downside regime gate + circuit-breakers — not systematic alpha.
- **7-day right tail** (leaderboard relevance): mean +0.4%, p95 +12.8%, max +21.8%, P(week > 15%) 4.0%.
- ~15 signal hypotheses (momentum, flow, whale-copy, funding, news-tilt, depeg, unlock, listing, squeeze, DEX/CEX lead-lag, LLM-allocator) were tested under walk-forward + locked holdout + cost and **rejected** as return-alpha. What survived: regime-gated DEX-liquid beta + bounded risk-control overlays (F&G guard, security veto, negative-news veto). The leaderboard play is convexity + not getting disqualified.

Reproduce: `python3 -m bnbhack_agent.cli track1-backtest`.
