# Track-1 Backtest Results (walk-forward, out-of-sample)

Universe: **64 eligible BEP-20 tokens** (Binance hourly price). Window: 2880 hourly bars, 2026-02-16 16:00:00+00:00 → 2026-06-16 15:00:00+00:00. Cost: 10 bps/turn simulated. Drawdown DQ gate: 30%.

All numbers below are **stitched out-of-sample**: on each 21-day train window the only hyperparameter (the regime MA) is chosen by Sharpe subject to the DD cap, then applied to the next 7-day window it never saw. The in-sample/OOS spread is reported as an overfit gauge.

## Result

| Strategy | OOS return | OOS Sharpe | OOS max DD |
|---|---:|---:|---:|
| **Regime-gated equal-weight (chosen)** | **+11.9%** | **1.50** | **14.7%** |
| Equal-weight basket (baseline) | +7.0% | 0.75 | 27.9% |
| BTC buy-and-hold | -2.4% | -0.02 | 28.0% |
| Cross-sectional momentum (REJECTED) | -63.1% | -4.14 | 67.8% |

## Why momentum was rejected

Naive top-K momentum rotation looks plausible in-sample (mean train return +4.8%) but collapses out-of-sample (-63.1%, Sharpe -4.14) — a textbook overfit. The walk-forward protocol exposes this instead of hiding it, which is the whole point.

## Chosen strategy

Hold a diversified equal-weight basket of the eligible tokens when BTC is above its regime MA; rotate fully to the stablecoin leg otherwise. MA chosen per fold (picks: [672, 672, 240, 240, 240, 240, 336, 336, 672, 672, 240, 240, 240, 336]). Across 14 OOS folds it beats the equal-weight baseline on return, roughly doubles Sharpe, and roughly halves drawdown — most profit without blowing up.

Reproduce: `python3 -m bnbhack_agent.cli track1-backtest`.
