# Track-1 Backtest Results (walk-forward, out-of-sample)

Universe: **64 eligible BEP-20 tokens** (Binance hourly price). Window: 2880 hourly bars, 2026-02-16 16:00:00+00:00 → 2026-06-16 15:00:00+00:00. Cost: 10 bps/turn simulated. Drawdown DQ gate: 30%.

All numbers below are **stitched out-of-sample**: on each 21-day train window the only hyperparameter (the regime MA) is chosen by Sharpe subject to the DD cap, then applied to the next 7-day window it never saw. The in-sample/OOS spread is reported as an overfit gauge.

## Result

| Strategy | OOS return | OOS Sharpe | OOS max DD |
|---|---:|---:|---:|
| **Regime-gated EW, top-10 liquid (LIVE strategy)** | **+16.5%** | **1.72** | **16.4%** |
| Regime-gated EW, full 64 | +11.9% | 1.50 | 14.7% |
| Equal-weight basket (baseline) | +7.0% | 0.75 | 27.9% |
| BTC buy-and-hold | -2.4% | -0.02 | 28.0% |
| Cross-sectional momentum (REJECTED) | -63.1% | -4.14 | 67.8% |

## Concentration — the leaderboard lever (spot-only, no leverage)

A winner-take-all 7-day contest rewards the right tail, not Sharpe. Concentrating the basket leaves expected return ~flat but fattens the weekly right tail, while the regime gate keeps the worst drawdown under the 30% DQ line. 7-day rolling-return distribution by basket size (random subsets, so this is the variance effect alone, not selection):

| Basket N | mean 7d | p95 7d | max 7d | P(week > 15%) |
|---:|---:|---:|---:|---:|
| 64 | +0.6% | +9.2% | **+13.8%** | 0.0% |
| 12 | +0.6% | +10.7% | **+24.0%** | 1.1% |
| 8 | +0.7% | +11.3% | **+24.2%** | 1.5% |
| 5 | +0.6% | +11.9% | **+28.1%** | 2.4% |

Live basket (top-10 liquid): ETH, ZEC, XRP, DOGE, UNI, ADA, TRX, XPL, BCH, INJ.

## Why momentum was rejected

Naive top-K momentum rotation looks plausible in-sample (mean train return +4.8%) but collapses out-of-sample (-63.1%, Sharpe -4.14) — a textbook overfit. The walk-forward protocol exposes this instead of hiding it, which is the whole point.

## Chosen strategy

Hold a diversified equal-weight basket of the eligible tokens when BTC is above its regime MA; rotate fully to the stablecoin leg otherwise. MA chosen per fold (picks: [672, 672, 240, 240, 240, 240, 336, 336, 672, 672, 240, 240, 240, 336]). Across 14 OOS folds it beats the equal-weight baseline on return, roughly doubles Sharpe, and roughly halves drawdown — most profit without blowing up.

Reproduce: `python3 -m bnbhack_agent.cli track1-backtest`.
