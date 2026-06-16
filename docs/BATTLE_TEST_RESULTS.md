# Battle-Test Results

This file records verified local strategy battle tests for the BNB Hack agent.

## BNB held-out battle

Command:

```bash
PYTHONPATH=src python3 -m bnbhack_agent.cli battle \
  --source binance \
  --symbols BNB \
  --count 1000 \
  --out runs/battle_bnb_real \
  --train-ratio 0.70
```

Output:

```text
best=pullback_rebound_s55_b46_x50 symbol=BNB test_return=16.19% test_sharpe=1.33 test_max_dd=2.96%
wrote runs/battle_bnb_real/battle_summary.json
wrote runs/battle_bnb_real/battle_report.md
```

Winner:

| Metric | Value |
|---|---:|
| Strategy | `pullback_rebound_s55_b46_x50` |
| Train return | 15.57% |
| Train Sharpe | 0.99 |
| Train max drawdown | 6.60% |
| Held-out return | 16.19% |
| Held-out Sharpe | 1.33 |
| Held-out max drawdown | 2.96% |
| Held-out turnover | 8 |
| Held-out exposure | 2.68% |
| Rule violations | 0 |
| Held-out buy-and-hold return | -25.87% |
| Held-out buy-and-hold max drawdown | 55.37% |

## Multi-symbol stress test

Command:

```bash
PYTHONPATH=src python3 -m bnbhack_agent.cli battle \
  --source binance \
  --symbols BNB,BTC,ETH \
  --count 1000 \
  --out runs/battle_multi_real \
  --train-ratio 0.70
```

Output:

```text
best=adaptive_trend_perps_f34_s144_lm65_sm40_tp30 symbol=ETH test_return=53.83% test_sharpe=1.58 test_max_dd=17.51%
wrote runs/battle_multi_real/battle_summary.json
wrote runs/battle_multi_real/battle_report.md
```

Baselines in that held-out window:

| Symbol | Buy-and-hold return | Buy-and-hold max DD |
|---|---:|---:|
| BNB | -25.82% | 55.37% |
| BTC | -46.97% | 49.53% |
| ETH | -58.77% | 63.73% |

## Interpretation

The strongest BNB-specific candidate is not a constant-exposure strategy. It waits for higher-timeframe trend support, enters pullbacks, and spends most of the held-out drawdown window in cash. That makes it useful for Track 2 because it is simple, backtestable, and rule-adherent.

The adaptive perps family matters for Track 1: it can take short exposure during downtrends, which is why it wins in the multi-symbol stress test.

These are backtests, not live PnL claims. The repo is designed so judges can replay the same strategy spec on a held-out window.
