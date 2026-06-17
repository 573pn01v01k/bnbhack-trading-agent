# Track-1 Backtest Results — live strategy (robust ensemble)

Universe: **64 eligible BEP-20 tokens** (Binance hourly). Window: 2880 bars, 2026-02-16 16:00:00+00:00 → 2026-06-16 15:00:00+00:00. Live config: model-averaged ensemble of regime-gated equal-weight over basket sizes N=(2, 3) × regime MAs=(240, 336, 480), rebalanced every 4h, 10.0bps cost.

The ensemble is anti-overfit by construction: it never selects an in-sample-best parameter, it averages over a grid. The locked 21-day holdout was never used to build it.

## Headline

| | Return | Sharpe | Max DD |
|---|---:|---:|---:|
| **Ensemble (live), full window** | **+20.0%** | **1.35** | **18.5%** |
| Ensemble, locked 21d holdout | +3.5% | 3.14 | 4.8% |
| Equal-weight baseline | +13.7% | 0.91 | 35.5% |
| BTC buy-and-hold | -2.9% | 0.01 | 28.0% |

## Cost sensitivity (turnover robustness)

| tx cost | full-window return |
|---:|---:|
| 0 bps | +23.6% |
| 10 bps | +20.0% |
| 20 bps | +16.5% |
| 40 bps | +9.9% |

The 4h rebalance keeps the book profitable through ~20bps of cost — hourly rebalancing did not (it churned the regime gate).

## Honest caveats — robustness validation

- **Returns are regime-dependent, not a stable edge.** Across three equal sub-periods: -12.3%, +39.5%, -1.9%. Almost all the profit comes from one trending window; the strategy loses or sits in cash otherwise. This is diversified crypto-beta capture with a downside regime gate — not systematic alpha.
- **7-day right tail** (leaderboard relevance): mean +1.5%, p95 +20.0%, max +27.0%, P(week > 15%) 10.2%.
- Naive momentum, reversal, vol-concentration, time-series momentum, adaptive sizing, and on-chain DEX-flow selection were all tested under the same walk-forward + holdout protocol and **rejected** (overfit or no edge). The ensemble is what survived.

Reproduce: `python3 -m bnbhack_agent.cli track1-backtest`.
