# Token-Unlock Fade (downside-avoidance) — convex hypothesis

**Date:** 2026-06-17 · **Window:** price panel 2026-02-16 → 2026-06-16 (hourly, 68 syms)

## Hypothesis
Large cliff unlocks create concentrated sell pressure. The convex play is AVOIDANCE:
drop/underweight a held token in the days around a big upcoming unlock. Small opportunity
cost, dodges a large drawdown. Forward-looking, so no lookahead by construction.

## Data reality / friction (honest)
- `get_token_unlocks(token_unlock, <slug>)` returns only the **single NEXT unlock** inline
  (date, cliff size, % of max supply). The full event list (incl. past dates needed for an
  event study) lives in an artifact whose body is **unreadable in this harness** —
  `read_artifact` and `download_artifact` return billing only, no payload. Confirmed twice.
- Many panel tokens use non-obvious DefiLlama slugs; several guesses 404'd (plume, world-liberty).
- Tool is concurrency-fragile (errors at >2 in-flight, phantom in-flight after completion) —
  forced strictly-serial calls, which capped how many tokens I could survey.

Net: I **cannot** build a clean multi-token historical event study from this tool here. I
fell back to the one token with a known, public, regular cadence — **ZRO/LayerZero, monthly
cliff on the 20th** — and measured realized behaviour from the cached price panel.

## Forward calendar gathered (inline summaries, point-in-time)
- **ZRO / layerzero**: next 2026-06-20, **2.3625% of max supply** to Core Contributors/Strategic
  Partners. 12 future events. ← only meaningful near-term cliff found; lands inside a contest
  window starting now.
- ASTER / aster: next 2026-06-30, 0.028% — trivial.
- PENDLE: no upcoming unlocks. STG (stargate-finance): fully unlocked, none upcoming.
  INJ slug empty in source.

## Proxy backtest — ZRO around its monthly-20th cliffs (n=4, single token)
2-day-pre run-up / 2-day-post drop around each unlock (daily closes):

| Unlock date | run-up t-2→t | post t→t+2 |
|---|---|---|
| 2026-02-20 | +11.9% | **-3.8%** |
| 2026-03-20 | -4.0% | **-5.5%** |
| 2026-04-20 | -6.2% | **-6.4%** |
| 2026-05-20 | +2.0% | **-5.4%** |

Post-unlock 2d return negative all 4 months, **mean -5.26%**. Looks like a clean convex dodge.

## Why it does NOT survive scrutiny
ZRO's **baseline** 2-day return over the full window: **mean -0.38%, sd 7.32% (n=119)** — the
token bled -34% over 4 months. The unlock-window mean of -5.26% is only **z = -1.33** vs that
baseline. The post-unlock drop is **statistically indistinguishable from ZRO's general
downtrend** at n=4. Incremental unlock-specific drawdown is maybe ~1-2%, with no confidence.

Avoidance "worked" here mostly because the token was in a persistent downtrend (regime beta),
not because of an identifiable unlock impulse — the same rejection pattern as the ~30 prior
symmetric signals (returns are regime-dependent beta). The opportunity cost of avoidance equals
the general drift; in an up-regime week, skipping the unlock day would have *cost* return.

## Asymmetry assessment
- Downside avoided per fire: ~5% nominal, but only ~1-2% is unlock-attributable; the rest is
  drift you'd also dodge (or wrongly dodge) on any random day. Round-trip TWAK cost 20-40bps
  must be paid each avoidance toggle.
- Upside (drawdown dodged) is small and not reliably > cost+noise. Not convex — it's a
  low-payoff, low-confidence directional bet dressed as risk management.

## Fires-per-week
Across the eligible panel, meaningful near-term cliffs (>~2% of supply within 7d) are **rare**:
in this survey only ZRO/06-20 qualified. Expect roughly **0–1 qualifying held-token unlock in a
random 7-day window**. A genuinely convex setup at this frequency could still be worth a rule —
but the payoff-when-fired here is too small/uncertain to clear cost.

## Verdict: REJECT (with one caveat-action)
No honest, lookahead-free evidence of an unlock-specific drawdown beyond regime beta; sample is
n=4 on a single downtrending token; the harness blocks the multi-token event study that could
overturn this. Edge does not clearly survive 20-40bps cost.

**Caveat-action (free, not a backtested edge):** since avoidance is forward-looking and
near-zero-cost when already underweight, a *defensive guardrail* — cap/zero the moonshot-sleeve
weight on any held token with a >2%-of-supply cliff inside the next 3 days (ZRO on 2026-06-20
being the live example) — is reasonable hygiene. It is risk hygiene, not alpha; do not size it
as a convex bet.
