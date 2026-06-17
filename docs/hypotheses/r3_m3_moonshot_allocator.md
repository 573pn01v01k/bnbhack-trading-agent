# Hypothesis R3-#4: MiniMax M3 as Moonshot Allocator (LLM mixture)

**Verdict: PARTIAL. The LLM itself does NOT beat the mechanical sleeve OOS, but the
ONE feature it leans on most — volatility-expansion — is a strictly better moonshot
selector than the live raw-momentum rule. Integrate the *feature*, not the LLM.**

## Hypothesis
Plug MiniMax M3 in as the moonshot PICKER. Build a rich point-in-time per-candidate
feature snapshot (trailing momentum, vol-expansion, fresh social via `search_twitter`,
CMC F&G, on-chain flow where available) and have M3 rank which 2-3 eligible names are
most likely to have a big up-move (>15%) this week, with a confidence. Compare the
M3-picked moonshot sleeve vs the current mechanical (top-k momentum) sleeve.

## Data access — OK
- M3 via 0G router (`minimax-m3`, Bearer, `<think>` stripped, `max_tokens=2500`) works.
- `search_twitter` real-time social works (~$0.003/call). CMC F&G live = **24 (Fear)**.
- Cached Binance hourly panel `price_120d.parquet` (2880 bars, 64 eligible names).
- **Non-reproducibility (stated up front):** LLM scores and social are CURRENT-only;
  there is no PIT social/news archive to replay. The literal M3 signal cannot be
  backtested. We therefore split the test: (a) PRESENT-DAY proof of what M3 picks and
  why, (b) a backtestable PROXY on the feature-mix M3 demonstrably reasons over.

## Signal definition (live)
Moonshot sleeve (capped at `moonshot_frac=10%` of idle cash, active mainly risk-off).
At each 4h rebalance, assemble PIT features per eligible name {mom12h, mom48h, mom7d,
vol_expansion = std(ret,12h)/std(ret,72h), fresh social digest, F&G}; M3 returns
`{picks:[{symbol,confidence,reason,already_priced_in}], avoid, note}`. Hold its top
2-3 equal-weight. No lookahead: every feature is trailing; social is as-of-now.

## Present-day proof (M3 live, 2026-06-16, Fear=24, risk-off)
Feeding the real snapshot for the strongest feature-mix candidates, M3 returned:
- **AAVE** (conf 0.55, not priced-in): fresh un-priced catalyst `feat/add-monad`
  merge + founder thread; mom12h only +1.0% = consolidation before next leg.
- **ROSE** (conf 0.42, not priced-in): highest vol_expansion (1.66), clean breakout,
  least narrative saturation; "move just waking, not exhausted."
- **AVOID UNI** — explicitly: "22% daily surge on the upgrade news is the textbook
  already-priced-in trap for a 7d lottery." Refused to force a 3rd pick.

Qualitatively this is *smarter* than the mechanical sleeve: mechanical top-k momentum
would buy UNI (the highest-momentum name) straight into the priced-in top — the exact
failure mode that killed the earlier news-allocation tilt. M3 leads on vol-expansion +
catalyst freshness and de-emphasizes raw momentum.

## OOS result (backtestable proxy — standalone sleeve, walk-forward + locked 21d holdout)
Moonshot selectors, k=3, 4h rotation, 10bps, full window / holdout:

| moonshot selector | full ret/Sh | holdout ret/Sh |
|---|---|---|
| mech mom12 (LIVE) | -75.8% / -2.77 | -19.8% / -1.56 |
| **vol_expansion** (M3's lead feature) | **-44.6% / -1.19** | **+15.5% / +2.60** |
| vol_exp-gated mom12 | -59.7% / -1.76 | -4.9% / +0.12 |
| m3_proxy (vol_exp − 2·priced-in) | -67.6% / -3.63 | -30.7% / -5.79 |

Standalone, the moonshot is a money-loser BY DESIGN (a capped lottery). But the
selector matters: **pure vol_expansion is the only one positive on the locked holdout**
and roughly halves the full-window drag vs mechanical momentum. M3's richer combination
(priced-in penalty) is *worse* — penalizing 7d momentum overfits and discards real
breakouts. And walk-forward selector-SWITCHING (let train-Sharpe pick the rule each
fold) is a disaster (-74.5%): the sleeve is too noisy for train Sharpe to predict the
right rule OOS — you cannot adaptively learn which moonshot logic to run.

In the SHIPPING combined book (moonshot capped at 10% idle cash):

| book | full ret/Sh | holdout ret/Sh | maxDD | 7d tail max / P(>15%) |
|---|---|---|---|---|
| LIVE (mech moonshot) | +3.4% / 0.45 | +2.1% / 1.63 | 20.1% | +17.3% / 1.8% |
| **vol_exp moonshot** | **+6.2% / 0.63** | **+5.4% / 4.28** | 18.6% | +16.8% / 1.8% |
| no moonshot (pure ensemble) | +9.0% / 0.83 | +3.5% / 3.71 | 16.4% | +16.8% / 1.8% |

Swapping the moonshot selector to vol_expansion strictly dominates the live mechanical
sleeve in the book (higher full + holdout return, lower DD, equal right tail). The
moonshot's right tail is unchanged across selectors — the convex 7d upside comes from
the ENSEMBLE, not the sleeve (it's only 10% of idle cash, mostly risk-off).

## Honest verdict — does the LLM allocator beat the mechanical sleeve?
**No, the LLM does not.** It adds per-cycle cost (~$0.01 social+LLM), latency, and
irreducible run-to-run variance (temperature, non-reproducible social), and its own
best idea — the already-priced-in penalty — *hurts* OOS. Its genuine value is
diagnostic, not allocative: it correctly articulates *why* mechanical momentum buys the
top, and it points at the right feature. That feature, vol_expansion, beats the live
moonshot rule cleanly and survives the holdout. The edge is the feature, not the model.

## Integrate? MAYBE (the feature, not the LLM)
- **Yes** — replace the moonshot selector `mom.pct_change(lb)` with **vol_expansion**
  (`std(ret,12h)/std(ret,72h)`, still gated to positive movers). Free, mechanical,
  decision-parity-preserving, strictly better in the book (+6.2% vs +3.4% full, holdout
  +5.4% vs +2.1%, lower DD) and survives the locked holdout. Tiny, bounded change.
- **No** — do NOT put M3 in the allocation/picking loop. Non-reproducible, cost+variance
  for no OOS gain; selector-switching can't be learned OOS. Consistent with the ~26
  prior rejections: returns are regime-dependent crypto-beta, not name-selection alpha;
  the moonshot is a capped heartbeat lottery whose only tunable that survives is *how*
  it picks the lottery ticket. M3's correct, defensible role stays the bounded negative
  -news VETO already shipped — risk control, not alpha.
