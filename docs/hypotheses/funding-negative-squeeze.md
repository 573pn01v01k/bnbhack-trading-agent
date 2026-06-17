# Extreme-Negative-Funding Squeeze-Long (CONVEX candidate)

**Verdict: REJECT.** Payoff *shape* is convex (downside hard-capped by stop, occasional +40% tails) but there
is **no positive expectancy** — every variant is net-negative after 30bps cost, and the out-of-sample
(last-21d) holdout is worse than train in *all* configurations. The convexity is a coin-selection lottery
carried by 1-3 names, not a tradeable edge.

## Hypothesis
When perp funding is very negative (shorts crowded, paying longs), there is asymmetric short-squeeze-up risk.
Go long when funding z-score is extreme-negative; cap downside with a stop, ride the squeeze tail.

## Signal (point-in-time, no lookahead)
- Bybit linear-perp funding history for 46 eligible tokens (those with both a perp and a price-panel column),
  2026-02-16 → 2026-06-16 (~17 weeks). 8h funding stamps.
- Rolling z-score `z = (fr - mean_60)/std_60` over the last 60 funding points (~20d), strictly trailing.
- Entry on the first hourly price bar AFTER the funding stamp is known (no settle-bar lookahead). Dedup 24–48h per coin.
- Forward window 24–48h. Stop-loss and take-profit simulated on the hourly path. Cost = 30bps round trip.

## Results (event-study + walk-forward holdout)
| Variant | n | fire/wk | net mean | win | best | worst | HOLDOUT net |
|---|---|---|---|---|---|---|---|
| z<=-2, 24h, no exit | 648 | 38.1 | -0.36% | 45% | +35% | -59% | -0.82% |
| z<=-3, 24h, no exit | 259 | 15.2 | -1.01% | 41% | +35% | -59% | -2.15% |
| z<=-2, 48h, stop5% tp25% | 643 | 37.8 | -0.09% | 43% | +25% | -5% | -0.99% |
| z<=-3 & fr<=-5bp, 48h, stop6% (RARE) | 86 | 5.1 | -0.76% | 31% | +45% | -6% | -1.20% |
| funding-rising-off-extreme trigger | 229 | 13.5 | -0.47% | 37% | +43% | -6% | -2.28% |

## Why it fails
- **Median trade is a loser** (RARE variant median net -3.47%, win rate 31%). Extreme-negative funding mostly
  marks tokens in a real downtrend where shorts are *correctly* positioned; price keeps bleeding into the stop.
  The squeeze is the exception, not the base rate.
- **Convex shape ≠ positive EV.** Stops cap worst to -5/-6% and tails reach +45%, but P(MFE>20%)=7% (RARE) /
  4% (trigger) — the rare squeezes don't pay for the frequent bleeds.
- **Concentration.** Total gains are carried by STG (39% of all positive), DUSK, ROSE. Removing STG flips the
  RARE net from -0.76% to -1.39%. Most coins are individually net-negative.
- **Holdout is uniformly worse than train** across every threshold/exit combo — the opposite of a robust edge.
- Tightening z, adding an absolute-funding filter, or waiting for funding normalization all leave it negative.

## Honest caveats
- 17-week span; the convex tails rest on ~6 events (P(MFE>20%) on 86 = ~6). Small-sample, but the direction
  (no EV, holdout decay, single-name concentration) is consistent enough to reject.
- This is the convex counterpart to the already-rejected funding-OVERHEAT idea and shares its fate: on this
  universe funding is regime-dependent beta, not a mean-predictive or convex signal.
