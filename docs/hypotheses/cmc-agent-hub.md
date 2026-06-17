# Hypothesis: CMC Agent Hub signals for moonshot selection + regime

**Date:** 2026-06-17  **Verdict:** No robust edge. One do-no-harm live overlay worth keeping; one defensible (but not OOS-proven) moonshot tweak; the headline pieces are inaccessible or inert in this regime.

## What was tested
Using the CMC Pro key (`.env`), three branches:
- **(a) TA-confirm moonshot movers** — only chase a mover if not overbought and volume expanding.
- **(b) Trending / gainers-losers** as moonshot candidate source.
- **(c) Global F&G / dominance / derivatives** as a market-regime input.

## Data access reality (the binding constraint)
- `/v3/fear-and-greed/latest` and **`/historical` work** — daily F&G back to 2025-05-13, fully overlaps the 120d panel, so (c) is genuinely backtestable.
- `/v1/global-metrics/quotes/latest` works (BTC dominance 58.3%, derivatives 24h vol, F&G snapshot).
- `/v2/cryptocurrency/quotes/latest` works and exposes `percent_change_1h/24h/7d`, `volume_24h`, `volume_change_24h` — but **snapshot only** (no per-token history on this tier). So the TA-confirm *logic* can run live, but can only be backtested via price-derived proxies (RSI, vol-expansion) on the cached panel.
- **`trending/latest` and `trending/gainers-losers` return 403** ("plan doesn't support this endpoint"). Branch (b) is not accessible on this key — a live gainers list can only be DIY-built from `listings/latest`, which is the same cross-sectional momentum already tested and rejected.

## Results (incumbent combined book = ensemble + capped moonshot; cost 10bps)

### (c) F&G regime overlay on the ensemble (point-in-time, daily ffill)
The 120d panel (Feb–Jun 2026) sat in Fear/Extreme-Fear almost throughout (F&G median ~24–40, max in-window ~50s). The greed-trim logic in `cmc.py` (trim at F&G>=70/80) **never fired** -> identical to incumbent (SEARCH +5.32% / HOLDOUT +3.46%). Variants that de-risk on rising F&G or cut on fear only *hurt* (binary off >40: SEARCH **-20%**) because the fear period was exactly when the ensemble earned. F&G adds nothing here; it is at best a euphoria guard that costs nothing when it never triggers.

### (a) Moonshot TA-confirm (price-derived RSI / vol-expansion proxies)
| variant | SEARCH ret | HOLDOUT ret |
|---|---:|---:|
| moon incumbent (chase positive mover) | +1.23% | +0.99% |
| + RSI<70 confirm | -0.99% | -1.51% |
| + RSI<80 confirm | +2.57% | -1.28% |
| **+ vol-expansion confirm** | **+3.26%** | **+3.51%** |
| + RSI<75 + vol-expansion | +5.11% | +2.77% |

RSI-not-overbought *hurts* (it filters out exactly the names that keep running). Vol-expansion confirm helps on both search and holdout. Sleeve-only, vol-expansion shrinks the moonshot's by-design loss from -70%/-29% to -51%/-7%.

### Robustness check (the protocol's real test)
Per 7-day OOS window, vol-expansion-confirm minus incumbent: **mean +0.33%, win-rate 43% (6/14 windows)**. The entire +3.26% search advantage comes from essentially **one window (+3.31%)**; most windows are 0 or slightly negative. Deployment frequency (2780 vs 2868 active bars) and turnover (0.0236 vs 0.0230/bar) are nearly identical, so the effect is not "trade less" — it is a small, regime-lucky right-tail capture that does **not** clear the robust-OOS bar.

## Live signal definitions (point-in-time, no lookahead)
- **F&G euphoria guard (keep):** at decision time pull `/v3/fear-and-greed/latest`; multiply ensemble exposure by 0.90 if F&G>=70, 0.80 if F&G>=80, else 1.0. Bounded, logged, never adds risk. (Already implemented in `cmc.regime_signal`; verified do-no-harm.)
- **Moonshot vol-expansion confirm (optional):** include a mover in the moonshot only if its trailing 12h return-std / 72h return-std > 1.0 at t (ignition proxy), in addition to the existing positive-momentum filter. Defensible and do-no-harm, but not OOS-proven.
- **Reject:** RSI-not-overbought filter (hurts); F&G de-risk-on-fear (hurts); gainers/trending selection (403, and equivalent to already-rejected cross-sectional momentum).

## Verdict
Does not add stable alpha over the regime-gated ensemble. Keep the F&G euphoria guard as a free, bounded overlay (it simply never fired in this fear regime). The vol-expansion moonshot confirm is the only tweak that even plausibly helps, and only as a sensible do-no-harm refinement of a deliberately negative-EV lottery sleeve — its apparent gain is one-window and fails the robustness test. Trending/gainers is paywalled on this key.
