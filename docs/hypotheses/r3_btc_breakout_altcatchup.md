# R3 NOVEL #2 — BTC-breakout alt-catchup ("catch the general upward movement")

**Verdict: REJECTED.** No alt catch-up edge after a fresh BTC breakout. When BTC prints a
new 48-96h high, the eligible alt basket *fades* at short horizons (negative mean, sub-50% hit
rate), and the only positive conditioning (BTC MA-cross-up) is just the incumbent's existing
risk-on regime gate restated. A "deploy on BTC breakout, cash otherwise" gate never beats the
incumbent regime-gated ensemble — it is strictly worse out-of-sample and identical on the holdout.

## Hypothesis

When BTC confirms an upside breakout (new N-h high, or crosses above its MA with positive
momentum), high-beta eligible alts catch up with a lag, so a regime-ENTRY trigger that tilts into
the basket on a fresh BTC up-break should capture asymmetric continuation. This is index/regime
*entry-timing* momentum, distinct from the already-rejected cross-sectional/time-series momentum.

## Method (point-in-time, no lookahead)

- Cached Binance hourly panel `price_120d.parquet` (2880 bars, 2026-02-16 → 2026-06-16), 64
  eligible BEP-20 candidates via `report._candidates`.
- BTC breakout flags, all known at bar t: `newhigh_{48,72,96}` (close ≥ max of the *prior* lb
  closes, `.shift(1)` so the current bar can't see itself) and `crossup_{168,240,336}` (BTC
  crosses from below to above its MA). "Fresh" event = rising edge of the flag.
- Event study: equal-weight alt-index forward return at h ∈ {6,12,24,48,96} after each fresh
  event, plus alt-minus-BTC (the catch-up test) and the unconditional baseline.
- Strategy variant: on a fresh `newhigh_lb` event turn the book ON for `hold` bars, cash
  otherwise; book = validated ensemble weights (already regime-gated) or plain EW basket.
- Walk-forward 21d-train / 7d-test over the (lb, hold) grid, DD-capped Sharpe selection,
  stitched OOS; locked last-21d holdout; cost curve. Net of cost (10bps base, 20-40bps stress).

## Results

### 1) Event study — the catch-up does not exist (it fades)
Fresh BTC **new-high** events: alt-basket forward returns are negative and below 50% hit-rate at
the horizons the hypothesis predicts a pop:

| event | n | alt h6 | hit h6 | alt h24 | hit h24 | alt h96 | altMinusBtc h96 |
|---|--:|--:|--:|--:|--:|--:|--:|
| newhigh_48 | 202 | -0.07% | 47.0% | -0.20% | 43.1% | +0.21% | +0.90% |
| newhigh_72 | 158 | -0.20% | 42.4% | -0.35% | 40.5% | +0.57% | +1.38% |
| newhigh_96 | 125 | -0.25% | 42.4% | -0.31% | 40.8% | +1.02% | +1.91% |
| **unconditional** | 2880 | +0.02% | 52.4% | +0.09% | 53.9% | +0.34% | +0.37% |

Right after a fresh BTC new-high, alts under-perform their own unconditional drift and lose more
often than a coin flip — the opposite of a lagged catch-up (looks like local exhaustion). A small
positive alt-minus-BTC appears only at h96, on 125-202 heavily-overlapping events (effective N far
smaller), too weak and too late to trade.

The `crossup_*` events do show ~60-63% hit at h48, but there are 1300+ of them — that is simply
"BTC is above its MA" (risk-on *state*), which the incumbent regime gate already harvests. It is
not a novel entry edge.

### 2) Strategy variant (full window, 10bps)
| strategy | return | Sharpe | maxDD |
|---|--:|--:|--:|
| incumbent ensemble | **+8.97%** | 0.83 | 16.4% |
| always-on EW basket | +5.49% | 0.57 | 27.9% |
| BTC buy-and-hold | -2.94% | 0.01 | 28.0% |
| breakout(lb=72,hold=96) ENS book | +10.42% | 0.94 | 16.4% (exposure 0.82) |
| breakout(lb=48,hold=168) ENS book | +13.21% | 1.12 | 16.4% (exposure 0.96) |

The only breakout variants that "beat" the incumbent do so at ~0.94-0.96 exposure — i.e. they are
the incumbent ensemble with a sliver of extra cash-timing, not a different edge. With the plain EW
book the gate is mostly flat-to-negative.

### 3) Walk-forward OOS (stitched, 14 folds) — strictly worse than incumbent
| | return | Sharpe | maxDD |
|---|--:|--:|--:|
| breakout-gate (WF-selected lb,hold) | +16.99% | 1.81 | 16.4% |
| **incumbent ensemble (same OOS bars)** | **+24.94%** | **2.44** | 16.4% |

The walk-forward gate underperforms the incumbent on every OOS metric. Selected params jump around
(48/168 → 48/72 → 48/48 → 96/48 …), the classic signature of no stable edge.

### Holdout (locked last 21d) and cost
All breakout variants are fully ON in the holdout, so they collapse to the incumbent: identical
+3.5% / Sharpe 3.71 / 3.2% DD (lb96/hold168 +3.6% is noise). Cost curve on the best full-window
variant: 0bps +14.3%, 10bps +10.4%, 20bps +6.7%, **40bps -0.5%** — survives base cost but turns
negative under stress, with no compensating edge over the cheaper incumbent.

## Conclusion

The "alts catch up after a BTC breakout" effect is absent on this universe/window. Fresh BTC
new-highs are followed by alt *under*-performance at short horizons; the only positive conditioner
is the risk-on MA state the incumbent already exploits. The breakout entry gate adds turnover and
timing risk while strictly underperforming the shipped regime-gated ensemble out-of-sample. Nothing
to integrate. The meta-finding holds: edge = regime-gated beta + capped moonshot, not regime-entry
timing.
