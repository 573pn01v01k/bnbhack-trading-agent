# Hypothesis: Stablecoin depeg -> re-peg (convexity)

**Date:** 2026-06-17  **Status:** REJECTED as standalone; thin MAYBE as a tiny capped sleeve.

## Idea
The eligible universe is stablecoin-heavy. When an eligible USD stable trades below
peg, buying it should be convex: downside ~capped (re-pegs to ~1.0), upside = the gap.

## Data
Binance hourly klines (close + intrabar low/high), ~16 months (Feb 2025 -> Jun 2026),
pulled directly (no MCP timeout risk). Eligible stables with a USDT spot pair:
USDC, FDUSD, TUSD, USDE, FRAX, USD1, XUSD, EURI.

Excluded:
- **USDT** — it is the numeraire (quote leg); cannot "depeg" in this frame.
- **EURI** — EUR-pegged; deviation vs USDT is FX, not a depeg.
- **TUSD ($5.6k/h vol), XUSD ($10k/h)** — untradeable, no real book.
- **FRAX** — min 0.269 / max 1.574 is a token redenomination/migration, NOT a depeg.
  Including it would be a lookahead/regime trap.

Liquid, genuinely-stable, tradeable set: **USDC, FDUSD, USD1, USDE**.

## Signal (point-in-time)
Resting limit bid at level L below peg; fill when an hour's `low <= L` (limit order
gets hit). Entry = L. Exit = limit sell at target (0.999-1.0) when `high >= target`,
else mark at close after max-hold. Round-trip cost charged at 30bps (mid of 20-40).
No lookahead: entry/exit use only that-hour OHLC.

## Results — the asymmetry inverts with depth

**Shallow bids (0.998-0.999):** fire often (0.5-0.7/wk) but net **NEGATIVE**. The peg
gap is smaller than cost+slippage, and most don't re-peg inside 72h. Picking up pennies.
- FDUSD bid@0.999, 72h: 51 fills, hit-peg 29%, net mean **-0.29%**, win 0%.
- USD1 bid@0.999: 37 fills, net mean **-0.24%**, win 0%.

**Deep bids (0.97), target 0.999, 48h hold — the only positive zone:**
| sym  | fills | /wk   | hit-peg | net mean | worst | MAE worst | dates |
|------|-------|-------|---------|----------|-------|-----------|-------|
| USDC | 0     | —     | —       | —        | —     | —         | never < 0.985 |
| FDUSD| 2     | 0.028 | 0%      | +2.45%   | +2.36%| **-10.0%**| 2025-04-02, 2025-09-24 |
| USD1 | 1     | 0.018 | 100%    | +2.69%   | +2.69%| -7.2%     | 2025-12-15 |
| USDE | 1     | 0.025 | 100%    | +2.69%   | +2.69%| **-33.0%**| 2025-10-10 |

Total: **4 events in 71 weeks** across all liquid stables.

## Why it's not the clean convex bet it looks like
1. **Tail is negative-skew, not capped.** "Downside capped at the gap" is FALSE for
   deep prints. USDE's worst intrabar MAE was **-33%** (10-Oct-2025 system-wide
   deleverage cascade; close 0.9365, full re-peg in 12h). FDUSD's Apr-2025 de-peg took
   **170h** to recover to 0.999 — longer than the 7-day contest window, so capital is
   trapped and marked down at settlement. A resting bid at 0.97 that fills on the way
   to 0.65 is sitting on a -28% unrealized mark.
2. **Two different regimes hide behind one signal.** Flash wicks (USDE/USD1) are
   V-shaped and recover in hours — genuinely convex. Sustained de-pegs (FDUSD) grind
   for days — concave inside the contest window. The signal can't tell them apart at
   entry.
3. **Sample is tiny.** 4 deep events, of which 1 is a structural event. No statistical
   confidence; the +2.7% "win rate 100%" is a 3-event artifact.

## Fires-per-week / contest framing
Deep bid@0.97: ~**0.07/wk combined** across all 4 stables.
**P(>=1 fire in a random 7-day window) = 5.7%** (493 daily-spaced windows). So in 94%
of contest weeks this sleeve does nothing, and when it does fire there is a real chance
it's the -10%/-33% leg rather than the +2.7% leg.

## Asymmetry (the actual convexity case)
Upside when fired: ~+2.5% to +2.7% net (peg gap minus 30bps), realized in <48h on
flash wicks. Downside: NOT capped at the gap — intrabar MAE reached -33% (USDE) and
-10% (FDUSD), and sustained de-pegs can stay underwater past the contest window. So
realized skew is roughly symmetric-to-negative, not convex. Convexity only holds for
the flash-wick subset, which is indistinguishable from the slow-bleed subset at entry.

## Net edge after cost
- Shallow (frequent) zone: negative after 30bps. Reject.
- Deep (rare) zone: +2.5%/event but the expected value is dominated by the unmodelled
  fat left tail and the 5.7% fire rate. Not a reliable contest edge.

## Verdict
**REJECT** as a standalone or sized strategy. The premise (capped downside) does not
survive the data: deep depegs carry an uncapped, slow-to-recover left tail, and the
positive zone is too rare (5.7% of contest windows) on too small a sample to bank on.

**MAYBE** only as a near-free lottery ticket inside the existing capped moonshot sleeve:
a tiny resting bid (<=0.5% of book) at ~0.985-0.99 on **USDC only** (the one stable
that never structurally broke; min close 0.985, deepest dips snap back fast). USDC's
discipline caps the left tail; the payoff-when-fired is small but the cost-of-carry is
~zero. Do NOT rest deep bids on USDE/FDUSD/USD1 — that is where the -10%/-33% tail lives.

## Reproduction
`/tmp/stable_data.pkl` holds the fetched panels; analysis is inline in the agent run
(Binance klines API, hourly). Cost = 30bps round trip.
