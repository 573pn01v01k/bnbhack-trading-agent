# Red-team Attack #3 — Concentration Fragility (N=2/3)

**Verdict: the headline edge is a single-name bet on ZEC. Severity HIGH for return
robustness, LOW for contest DQ. The intuitive "exclude pumped names" fix is
cost-negative (it removes the only alpha). A minimum-names floor cuts single-name
dependence ~40% but at a real return haircut. Integrate: MAYBE (small sample).**

## Setup
- Book: `combined_weights` / `ensemble_weights`, `ensemble_ns=(2,3)`, `max_weight=0.50`,
  MAs (240/336/480), 4h rebalance, +moonshot sleeve.
- Ranked liquid pool (top-12, stables excluded): `ETH, ZEC, XRP, DOGE, UNI, ADA, TRX, XPL, BCH, INJ, TON, LINK`.
  The convex sleeves only ever touch the top ~3: **ETH, ZEC, XRP**.
- Price cache `price_120d.parquet` (2880h, 68 cols). Cost stressed at both 10bps (brief
  headline) and 30bps (brief's backtest assumption).
- Mean book weights: **ZEC 0.249, ETH 0.244, XRP 0.098** — ZEC and ETH co-dominate.

## Finding — the +20% is ZEC

Full-window per-name returns: **ZEC +72.7%**, ETH -9.7%, XRP -18.4%, DOGE -13.8%, UNI -12.9%.
ZEC is the only top name that went up; it carries the book.

Drop-one perturbation (combined book, 30bps):

| Drop | Total return | Δ vs base |
|------|-------------:|----------:|
| (base)| +1.8% | — |
| ETH | -0.7% | -2.5% |
| **ZEC** | **-20.0%** | **-21.8%** |
| XRP | +2.1% | +0.3% |

Ensemble-only (no moonshot), the brief's +20% headline reproduces at 10bps (+20.0%);
removing ZEC turns it into **-9.2%** (10bps) / **+13.2%→-20.0%** (30bps).

Random subset test (drop 4 of top-12, 200 draws, 30bps): subsets that **include ZEC
average +3.4%**, subsets **without ZEC average -17.7%** — a 21pp swing attributable to one name.

Single-name concentration is real and the entire realized edge rests on ZEC pumping
in this specific window.

## Drawdown / DQ nuance (good news)
- 21-day holdout (30bps): combined book -20.1% return, **maxDD 33.9% — breaches the 30% DQ gate**.
- BUT the contest unit is ONE 7-day window. Across all 114 overlapping 7d windows
  (daily step), **0 breach 30%**; worst intra-window DD = 14.4%. The 34% was a 21-day artifact.
- So concentration's DQ risk for the actual contest format is LOW; the exposure is
  return *dispersion*, not blowup.

## Fix attempted #1 (rejected) — exclude/de-rank names that pumped >X% in prior window
Point-in-time: at each bar, demote any candidate whose trailing 168h return > thr to
the back of the ranked list. Results (ensemble-only, 30bps; base +13.2%):

| thr / floor | full-window return |
|-------------|-------------------:|
| 0.40 / 3 | +1.9% |
| 0.50 / 3 | +0.3% |
| 0.60 / 4 | +5.0% |
| 0.40 / 4 | +3.6% |

**Cost-negative.** The name that drives the book (ZEC) *is* the pumped name, so excluding
pumps removes the alpha. Rejected — momentum continuation, not mean-reversion, paid here.

## Fix proposed — minimum-names floor (widen `ensemble_ns`, lower `max_weight`)
Keeps the convex tail (still concentrated in the top-liquid names) but forces the basket
wider so no single miss sinks it. Ensemble-only, 30bps:

| Config | Full | maxDD | no-ZEC | ZEC-gap | holdout-21 DD | 7d max/min |
|--------|-----:|------:|-------:|--------:|--------------:|-----------:|
| **SHIPPED ns(2,3) mw0.50** | +13.2% | 20% | -8.5% | **+22pp** | **34% (DQ)** | +14/-10% |
| FLOOR ns(3,4) mw0.40 | +5.5% | 19% | -7.9% | +13pp | 29% | +11/-9% |
| FLOOR ns(3,5) mw0.34 | +5.7% | 19% | -9.5% | +15pp | 29% | +12/-8% |
| FLOOR ns(4,6) mw0.30 | +0.6% | 19% | -6.1% | +7pp | 28% | +10/-8% |

`ns(3,4)/mw0.40` roughly halves single-name (ZEC) dependence (gap +22pp→+13pp) and pulls
the 21-day holdout DD back under the gate (34%→29%), keeping a positive right tail (+11%).
The pumped name is still held (no alpha thrown away) — it's just no longer 50% of the book.

## Fix validation (walk-forward / per-window, net of 30bps cost)
Non-overlapping 7d windows (n=17), and overlapping daily-step DQ:

| | per-7d mean | std | min | max | single-7d DQ | overlap-7d maxDD |
|--|-----------:|----:|----:|----:|:------------:|-----------------:|
| SHIPPED | +1.24% | 6.76% | -9.65% | +14.08% | 0/17 | 14.4% |
| FLOOR(3,4)/0.40 | +0.74% | 5.68% | -8.94% | +10.76% | 0/17 | 13.5% |

The floor cuts per-window return dispersion ~16% (std 6.76→5.68) and trims the worst
window (-9.65→-8.94), at the cost of mean per-window return (+1.24→+0.74) and tail
peak (+14→+11). Neither config DQs in a single 7d window.

## Honest verdict
- The fragility is **real and severe for return robustness**: +20% is one name (ZEC).
  In a random 7d contest window where ZEC does not pump, the book is roughly flat-to-down.
- It is **not** a DQ risk for the contest's single-7d format (0/114 breaches).
- The "exclude pumped names" fix is cost-negative — rejected.
- The minimum-names floor is a genuine robustness improvement (≈40% less single-name
  dependence, holdout DD back under gate, lower dispersion) but it is a return-for-safety
  trade and the validation sample is tiny (17 non-overlapping windows). Whether to ship
  depends on risk appetite: SHIPPED maximizes expected leaderboard rank if you accept that
  the outcome is a coin-flip on one name; FLOOR trades peak for a tighter, less ZEC-levered
  distribution. Recommend FLOOR ns(3,4)/mw0.40 only if the team prefers dispersion control
  over max upside; otherwise keep SHIPPED but DO NOT believe the +20% is robust.
