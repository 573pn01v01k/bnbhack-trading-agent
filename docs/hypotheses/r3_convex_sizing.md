# R3 / Novel #5 — Convex sizing for the 1-week right tail

**Question.** The contest is one random 7-day window where a big hit wins. Rather than
add a new signal, tune the *convex structure* of the SHIPPED book (regime-gated EW
ENSEMBLE + capped moonshot) to fatten the right tail — P(week>10/15/20%), p95, max —
while keeping worst-week drawdown under the 30% DQ gate and median bleed bounded.

**Protocol.** Live book = `strategy.combined_weights` (ensemble + idle-cash moonshot).
No-lookahead via `portfolio.strategy_returns` (weights shift one bar). Cached Binance
hourly panel `price_120d.parquet` (2880 bars, 64 eligible BEP-20 candidates, 2026-02-16
→ 2026-06-16). 7-day windows (H=168h): overlapping every 6h (n=452) and **non-overlapping
(n=17, the honest independent sample)**. Net of 30bps TWAK (also checked 10/20/40bps).
Locked last-21d holdout reported separately.

## Sweep 1 — moonshot_frac × moonshot_k (flat vs vol-targeted)
Pushing the moonshot sleeve does **not** fatten the right tail. p95 barely moves
(0.136→0.143), max is pinned at the ensemble's own best week (0.183) until frac=0.40/k=1,
and that only reaches max=0.22 at the cost of worst-week DD=0.48, full DD=0.61 — **breaks
the gate**. Median bleed worsens monotonically with frac. Vol-targeting the idle-cash
deployment *caps* the very upside it is meant to protect (worse, not better). The
moonshot sleeve is downside-capped lottery on *idle cash only*; it cannot move the
right tail because the right tail comes from the **core ensemble**, not the sleeve.
**Recommendation: leave moonshot_frac at 0.10, k at 3.**

## Sweep 2 — barbell / core concentration (the productive lever)
Concentrating the ensemble into spikier small-N sleeves with a relaxed per-name cap
is where the tail actually fattens. Net of 30bps, overlapping windows:

| config | mean | median | p95 | max | P>10% | P>15% | P>20% | worst-wk DD | full DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SHIPPED N=(3,5,8) cap0.34 | -0.4% | -1.5% | 13.6% | 18.3% | 10.0% | 2.0% | 0.0% | 14.3% | 23.6% |
| **N=(2,3) cap0.50** | **+0.4%** | -1.9% | **21.1%** | **27.0%** | **14.4%** | **10.6%** | **6.4%** | 15.7% | 25.6% |
| N=(2,3,4) cap0.50 | +0.2% | -1.7% | 18.6% | 23.8% | 9.3% | 9.3% | 1.8% | 15.0% | 25.1% |
| N=(1,2,3) cap0.60 | -2.3% | -3.3% | 12.2% | 18.0% | 9.3% | 1.3% | 0.0% | 20.0% | **41.6%** ✗ |
| N=(2,3) + moonshot 0.20 | -0.6% | -2.9% | 20.9% | 27.7% | 14.6% | 10.8% | 6.4% | 19.1% | 31.6% ✗ |

The winner **N=(2,3), cap=0.50** roughly **5×'s P(week>15%) (2.0%→10.6%)** and creates a
**6.4% chance of a >20% week from zero**, while lifting median bleed only marginally
(-1.5%→-1.9%) and *keeping worst-week DD at 15.7% and full-window DD at 25.6% — both
inside the 30% gate*. Mean turns slightly positive. Over-concentration N=(1,2,3)
breaks the gate (full DD 41.6%); adding moonshot frac on top adds DD with no extra tail.

cap=0.50 ≡ cap=0.60 (the 2-name sleeve binds at 0.50 each), so 0.50 is the natural value.

## Robustness
- **Cost 10/20/30/40bps:** p95 21.8%→20.9%, max 27.6%→26.7%, P>15% flat at 10.6%, full
  DD 22.2%→27.2% (under gate at all costs). Mean stays ≥0 through 40bps. Cost-robust.
- **Non-overlapping 7d (n=17, independent sample):** p95 15.0%, max 15.5%, P>15% 5.9%,
  P>20% 0.0%. The >20% hits in the overlapping view **cluster in one trending stretch** —
  episodic, not stationary. Mean positive (+0.5% at 30bps).
- **Locked 21-day holdout:** worst-week DD identical to SHIPPED (8.4%), tail marginally
  better, no degradation. Does not break the locked test.

## Verdict — INTEGRATE (concentration only)
Adopt **`ensemble_ns=(2,3)`, `max_weight=0.50`**, leave `moonshot_frac=0.10`, `moonshot_k=3`.
This is sizing of an already-validated book (low overfit): it preserves the regime gate
and DD discipline while ~5×'ing the >15% weekly tail and minting a 6.4% chance of a >20%
week — exactly the convex profile a single random 7-day contest window rewards. The
moonshot sleeve and vol-targeting are dead ends for the tail and should stay as-is.

**Honesty:** the fat tail rests on only ~17 independent 7-day windows over 120d; the
>20% mass is episodic (one trending regime). The trade is a thinner, spikier core, so a
*non-trending* contest week bleeds slightly more (median -1.9% vs -1.5%) — accepted, since
the objective is the right tail under a hard DD gate, both of which hold.
