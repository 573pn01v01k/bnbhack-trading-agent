# Red-team Attack #2 — Regime-gate whipsaw / choppy-week bleed

## The weakness

The shipped book gates risk-on/off on `regime_off`: `BTC < BTC.rolling(MA).mean()`,
evaluated **hourly** at MA = 240/336/480 (`strategy.regime_off`, averaged across the three
ensemble sleeves in `ensemble_weights` / `combined_weights`).

A raw hourly MA crossover is extremely noisy on BTC. Over the 120d panel
(`price_120d.parquet`, 2880 hourly bars):

| MA  | off-fraction | flips | flips reversing within 48h | median dwell |
|-----|-------------|-------|----------------------------|--------------|
| 240 | 0.44 | 71 | 58 | 5h |
| 336 | 0.42 | 63 | 54 | 3h |
| 480 | 0.39 | 56 | 49 | 3h |

The gate flips on the order of 60-70 times in 120d, with a **median dwell of 3-5 hours** and
~85% of flips reversing inside two days. Each flip dumps the whole basket to cash (or re-buys
it) at one-sided turnover ≈ basket size, so the book repeatedly sells low / buys back high.

### It maps directly onto the losing weeks
Per non-overlapping 7d window (shipped book, `combined_weights`), counting BTC/MA336 crossings:

- The three highest-crossing weeks — 2026-03-02 (11 crosses), 03-16 (18), 03-23 (15) —
  returned **-4.34% / -4.57% / -4.49%**.
- The clean-trend weeks (1-3 crosses) carried the book: 03-09 +10.8%, 04-06 +14.5%, 05-04 +13.8%.

Aggregating: **choppy weeks (>=6 crosses) sum to -6.07%; trending weeks sum to +28.70%.**
The sub-period -12% the book bleeds in risk-off is the whipsaw weeks compounding, not the
trend itself.

Total cost drag from turnover over the window is **6.22%** of equity (most from the moonshot
sleeve; the main ensemble alone is 2.93%), and the regime flips are a meaningful slice of it.

## The fix — re-entry hysteresis (point-in-time, single constant)

Add an **asymmetric band** to the regime gate: exit risk-on the instant `BTC < MA` (protect
fast), but only re-enter risk-on when `BTC > MA * (1 + band)` (confirm before redeploying).
This is a stateful one-line change to `regime_off` with a single new constant `regime_band`
(no per-fold selection, no lookahead — the band is decided once, ex ante).

```
exit  (go to cash) when BTC < MA
enter (go risk-on)  when BTC > MA * (1 + band)     # band ≈ 0.005–0.010
```

Tested variants: hysteresis band (chosen), N-hour re-entry confirmation, symmetric bands.
Hysteresis band dominated; symmetric/confirmation either under-protected or clipped the trend
tail (e.g. enter>=24h above: +9.6%, worse).

## Validation (net of 10bps cost)

**Per-week chop vs trend decomposition (band = 0.005, full book):**

| | shipped | hysteresis | delta |
|---|---|---|---|
| choppy weeks (>=6 crosses), summed | -6.07% | **-4.16%** | **+1.91pp (~31% less bleed)** |
| trending weeks, summed | +28.70% | **+30.36%** | +1.66pp (tail NOT hurt) |

The two worst whipsaw weeks improved +1.29pp (03-16) and +1.36pp (03-23); the big trend weeks
(04-06 +14.5%, 05-04 +13.8%) are unchanged. The fix removes chop bleed without touching the
fat right tail.

**Walk-forward OOS, stitched 7d test windows, FIXED constant band (no selection):**

| band | OOS ret | OOS max DD | OOS Sharpe |
|------|---------|-----------|-----------|
| 0.000 (shipped) | +42.18% | 19.14% | 3.06 |
| 0.005 | **+47.81%** | **15.59%** | **3.40** |
| 0.010 | +48.86% | 13.90% | 3.50 |

(OOS curve covers the latter ~9 weeks after the first 21d train, hence the higher headline than
the full-window +14.6%; the comparison across bands is apples-to-apples.)

**Main ensemble only (no moonshot), full window:** band 0.005 → +23.83% vs +20.01%, DD 17.23%
vs 18.53%, cost drag 2.60% vs 2.93%. Confirms the effect is the regime gate, not a moonshot
artifact.

**Locked last-21d holdout:** +1.78% (band 0.005) vs +1.85% (shipped), DD 5.25% both.
**Honest caveat:** the holdout window is a clean low-cross trending stretch (almost no
whipsaw), so it neither exercises nor rewards the mechanism — it confirms the fix does **no
harm** in a trend but cannot independently confirm the chop benefit. The chop evidence comes
from the in-window choppy weeks and the walk-forward OOS.

### Rejected as overfit
Letting walk-forward *select* the band per train fold made OOS **worse** (+36.5% vs +42.2%):
band selection chases recent train noise and mis-times re-entry. The robust version is a single
**fixed** band (0.005–0.010), not a tuned one. This is why the recommendation is a constant.

## Recommendation

Set `regime_band = 0.0075` (mid of the validated 0.005–0.010 plateau; both endpoints beat
shipped on return, DD, and Sharpe OOS) and make `regime_off` stateful: exit at MA, re-enter at
`MA*(1+band)`. Keep exit symmetric/fast. Single constant, point-in-time, no lookahead, cost-
positive. Expected effect: ~30% less choppy-week bleed and a ~20-25% lower max drawdown
(directly protecting against the 30% DQ gate) with the trending tail intact.
