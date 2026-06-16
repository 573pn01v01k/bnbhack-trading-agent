# Auto-Research Log

Walk-forward OOS on the search window (last 21 days locked as holdout). A new strategy is promoted only if it beats the incumbent OOS return by >3pp, respects the 30% DD cap, AND survives the locked holdout. Every hypothesis tested is recorded — the count is the multiple-comparison budget.

## Iteration 1 (2026-06-16 16:59 UTC)

| hypothesis | OOS return | OOS Sharpe | OOS max DD |
|---|---:|---:|---:|
| `regime_ew_top5` ⭐ | +14.8% | 1.69 | 20.2% |
| `regime_ew_top15` | +12.3% | 1.61 | 15.6% |
| `regime_ew_top10` | +11.8% | 1.54 | 16.4% |
| `regime_ew_top64` | +11.5% | 1.66 | 14.7% |
| `momo_riskon_top20` | +6.8% | 0.83 | 32.9% |
| `highvol_pit_top12` | +6.4% | 0.89 | 17.9% |
| `regime_ew_top8` | +5.8% | 0.86 | 17.7% |
| `invvol_top15` | +5.8% | 1.02 | 13.3% |
| `vol_expansion_top8` | +2.0% | 0.45 | 22.2% |
| `ew_breadth_top10` | -9.2% | -1.11 | 18.2% |
| `highvol_pit_top8` | -14.8% | -1.13 | 24.7% |

No promotion — incumbent `regime_ew_top10` (+11.8%) holds (no hypothesis cleared +3pp margin OOS).
Holdout check of `regime_ew_top5`: -17.1% / Sharpe -3.82 / DD 28.4%.

## Iteration 2 (2026-06-16 18:23 UTC)

| hypothesis | OOS return | OOS Sharpe | OOS max DD |
|---|---:|---:|---:|
| `regime_ew_top5` ⭐ | +14.8% | 1.69 | 20.2% |
| `regime_ew_top15` | +12.3% | 1.61 | 15.6% |
| `regime_ew_top10` | +11.8% | 1.54 | 16.4% |
| `regime_ew_top64` | +11.5% | 1.66 | 14.7% |
| `momo_riskon_top20` | +6.8% | 0.83 | 32.9% |
| `highvol_pit_top12` | +6.4% | 0.89 | 17.9% |
| `regime_ew_top8` | +5.8% | 0.86 | 17.7% |
| `invvol_top15` | +5.8% | 1.02 | 13.3% |
| `vol_expansion_top8` | +2.0% | 0.45 | 22.2% |
| `trend_scaled` | -2.8% | -0.39 | 12.3% |
| `ts_momentum_top15` | -8.3% | -0.84 | 24.6% |
| `ew_breadth_top10` | -9.2% | -1.11 | 18.2% |
| `ts_momentum` | -10.1% | -1.26 | 19.3% |
| `highvol_pit_top8` | -14.8% | -1.13 | 24.7% |

No promotion — incumbent `regime_ew_top10` (+11.8%) holds (no hypothesis cleared +3pp margin OOS).
Holdout check of `regime_ew_top5`: -17.1% / Sharpe -3.82 / DD 28.4%.

