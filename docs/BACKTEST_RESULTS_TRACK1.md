# Track-1 Backtest Results — live strategy (robust ensemble)

Universe: **64 eligible BEP-20 tokens** (Binance hourly). Window: 2880 bars, 2026-02-16 16:00:00+00:00 → 2026-06-16 15:00:00+00:00. Live config: model-averaged ensemble of regime-gated equal-weight over basket sizes N=(3, 5, 8) × regime MAs=(240, 336, 480), rebalanced every 4h, 10.0bps cost.

The ensemble is anti-overfit by construction: it never selects an in-sample-best parameter, it averages over a grid. The locked 21-day holdout was never used to build it.

## Headline

| | Return | Sharpe | Max DD |
|---|---:|---:|---:|
| **Ensemble (live), full window** | **+9.0%** | **0.83** | **16.4%** |
| Ensemble, locked 21d holdout | +3.5% | 3.71 | 3.2% |
| Equal-weight baseline | -0.7% | 0.26 | 34.6% |
| BTC buy-and-hold | -2.9% | 0.01 | 28.0% |

## Cost sensitivity (turnover robustness)

| tx cost | full-window return |
|---:|---:|
| 0 bps | +12.2% |
| 10 bps | +9.0% |
| 20 bps | +5.8% |
| 40 bps | -0.2% |

The 4h rebalance keeps the book profitable through ~20bps of cost — hourly rebalancing did not (it churned the regime gate).

## Honest caveats — robustness validation

- **Returns are regime-dependent, not a stable edge.** Across three equal sub-periods: -9.9%, +20.4%, +0.5%. Almost all the profit comes from one trending window; the strategy loses or sits in cash otherwise. This is diversified crypto-beta capture with a downside regime gate — not systematic alpha.
- **7-day right tail** (leaderboard relevance): mean +0.7%, p95 +12.6%, max +16.8%, P(week > 15%) 1.8%.
- Naive momentum, reversal, vol-concentration, time-series momentum, adaptive sizing, and on-chain DEX-flow selection were all tested under the same walk-forward + holdout protocol and **rejected** (overfit or no edge). The ensemble is what survived.

Reproduce: `python3 -m bnbhack_agent.cli track1-backtest`.
