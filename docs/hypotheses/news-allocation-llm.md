# Hypothesis: News → Allocation (LLM-scored catalyst tilt)

**Verdict: NO EDGE. Reject.** Adds turnover cost without selection edge; the
mechanism is structurally lagged and the proxy fails the locked holdout.

## Hypothesis
Pull recent news/social per eligible token, score materiality/sentiment with an
LLM (MiniMax M3 via 0G Labs), and tilt allocation toward tokens with a fresh,
material, positive catalyst. Thesis: catalysts predict near-term outperformance.

## Data access
- **MiniMax M3 works** via 0G router `https://router-api.0g.ai/v1/chat/completions`
  (OpenAI-compatible, `model=minimax-m3`, Bearer = `MINIMAX_M3_API_KEY`). Note: M3
  emits a `<think>` block, so set `max_tokens >= 2000` and strip before `</think>`.
- **Monolit `search_twitter`** returns real-time, ranked social — works well (~$0.003/call).
- **CMC news/trending/content endpoints are plan-gated** (error 1006) on this key.
  Fear & Greed, quotes, listings work (F&G today = 23, "Fear").
- **News history is NOT point-in-time retrievable.** Social/news search APIs return
  *current* sentiment only; there is no clean 120-day per-token news archive with
  timestamps we can replay without lookahead. This alone makes a direct backtest of
  the literal signal impossible — stated honestly.

## Backtestable? PARTIAL (proxy only)
The literal LLM-news signal cannot be backtested (no PIT news history, and LLM
scores are non-reproducible). Instead we backtested the **mechanism** it triggers
on with a generous upper-bound proxy: a fresh catalyst leaves a price+volume
footprint in the same bar, so we used the trailing 12/24/48h return burst (known
at t, no lookahead) as the catalyst detector and tilted toward it. If even this
idealized, less-noisy, non-lagged proxy fails, the LLM layer (strictly noisier and
more lagged) cannot rescue it.

## Signal definition (live)
At each rebalance t: for each eligible token, fetch fresh social/news (search_twitter),
score with M3 → {materiality 0-10, sentiment -1..1, fresh_catalyst, already_priced_in}.
Overweight names with materiality high, sentiment > 0, already_priced_in false.
Backtest proxy: `burst = price.pct_change(lb)`; multiply EW weight of the top-`top`
burst names by `tilt`, renormalize, regime-gate (BTC < MA → cash), 4h rebalance, 10bps.

## OOS result (walk-forward search window + LOCKED 21-day holdout)
Incumbent ensemble: **search +5.3% / Sh 0.64; holdout +3.5% / Sh 3.71 / DD 3.2%.**

| variant | search ret/Sh | holdout ret/Sh |
|---|---|---|
| tilt lb=24 x1.5 top4/12 | +6.3% / 0.73 | +2.0% / 1.96 |
| tilt lb=48 x2.0 top4/12 | +8.4% / 0.89 | +1.5% / 1.51 |
| tilt lb=48 x3.0 top4/12 | +9.7% / 0.97 | +1.0% / 1.06 |
| catalyst-ONLY lb=24 top8/64 | -17.2% / -0.87 | -1.4% / -0.99 |
| catalyst-ONLY lb=48 top8/64 | +7.5% / 0.75 | **-3.2% / -2.41** |

Reading:
- Stronger search return comes only from a more aggressive tilt — classic in-sample
  param mining. **Every tilt variant underperforms the incumbent on the locked
  holdout**, and degrades monotonically as the tilt strengthens.
- Pure catalyst-chasing is a disaster (-17% to -29% search; the one positive search
  config flips to -3.2% holdout). Chasing already-moved names = buying the top;
  mean reversion + turnover cost punish it.

## Present-day proof (M3 live scoring)
Top fresh catalysts right now, scored by M3:
- **ZEC**: materiality 6, sentiment +0.8, fresh_catalyst true, **already_priced_in TRUE**
  (Anthropic/Mythos AI audit + erased June-4 vuln sell-off, +27% in one session).
- **XPL**: materiality 7, sentiment +0.85, fresh_catalyst true, **already_priced_in TRUE**
  (Plasma One card launch next week, +30% intraday — "anticipation largely priced in").

The signal would overweight ZEC and XPL — but **both are already the incumbent's
top-3 holdings** (liquidity-ranked EW already captured them). The tilt would only
add turnover cost (10-30 bps) to chase a move that has already happened. The LLM
itself flags `already_priced_in: true` — it correctly recognizes the signal is
coincident/lagging, not leading.

## Why it fails (mechanism)
By the time a catalyst is observable — in price, in news, or to an LLM — the move
is largely complete. News is a *more* lagged, noisier version of the price-burst
proxy that already failed the holdout. This is consistent with the ~25 prior
rejections (momentum, vol-concentration, DEX-flow selection): returns are
regime-dependent crypto-beta, not name-selection alpha. Catalyst-chasing adds
turnover without selection edge.

## Integrate? NO
Do not add as an allocation tilt. The only defensible use is a **bounded live veto**
(like the existing security/flow overlay): M3 could flag a held name with a fresh
*negative* materiality event (hack, depeg, delisting, exploit) to drop it — risk
control, not alpha. That is narrow, asymmetric, and doesn't chase pumps. As an
overweight signal it is rejected.
