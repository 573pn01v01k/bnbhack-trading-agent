# Red-team validation — the always-invested core sleeve under tail stress

The `core_ew_frac` sleeve (default 0.30) is the one mechanism that holds risk **regardless of
regime** — it is always invested, protected only by the 20% per-name trailing stop. The concern:
does that always-on exposure break DQ-safety in a sharp crash that the regime gate would otherwise
sidestep? Tested by injecting a synthetic market-wide crash over 24h mid-panel and recomputing the
live book end-to-end (DEX-liquid candidates → blended weights → per-name realistic cost).

| Scenario | Book drawdown around the event | Verdict |
|---|---:|---|
| Baseline (full window, no injection) | 15.9% | safe |
| Worst real 7-day rolling window in-sample | 13.0% | safe |
| Injected **−35%** market crash / 24h | 17.1% | safe |
| Injected **−45%** market crash / 24h | 17.4% | safe |
| Injected **−60%** market crash / 24h | **18.0%** | **safe** |

**Why drawdown barely moves even for a −60% crash.** Two protections compound:
1. The regime-gated ensemble (≈70% of the book) rotates to cash as BTC breaks its MA — that sleeve
   is out of the market for the crash.
2. The 20% per-name trailing stop caps each always-invested core name's loss to ~20% from its peak,
   so the 30% core contributes at most ~30% × 20% ≈ 6% to drawdown before it is in cash.

Net: even a −60% market event lands the book at ~18% drawdown — inside the 30% disqualification gate
with headroom. The core sleeve adds expected return (full −2.2% → +4.3%) **without** trading away the
survival property that is the whole point of the design. Reproduce with the stress harness inline in
the iteration log; the protections are `strategy.regime_off` (hysteresis gate) + `strategy.apply_trailing_stop`.
