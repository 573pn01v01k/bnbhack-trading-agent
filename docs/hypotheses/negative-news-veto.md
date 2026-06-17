# Hypothesis: Negative-News Veto (held-token catastrophe avoidance)

**Verdict: KEEPER. Integrate as a bounded, logged risk-control overlay (default ON).**
This is the asymmetric/convex use of the LLM-news layer that the prior
catalyst-tilt round (`news-allocation-llm.md`) explicitly flagged as the only
defensible application: not alpha selection, but dropping a held name to cash
when a fresh severe negative event hits.

## Hypothesis
At each rebalance, for the tokens the strategy actually HOLDS, fetch fresh
social/news (Monolit `search_twitter`) and score with MiniMax M3 (0G router) ->
`{negative_event: bool, category, severity 0-10}`. If a held name has a fresh
severe negative event (hack / exploit / depeg / delisting / regulatory / rug,
severity >= 6), add it to the strategy `vetoes` set so the ensemble allocates it
to cash that cycle. Asymmetry: tiny opportunity cost vs. avoiding a -30/-60%
position-level catastrophe.

## Data access — OK
- **MiniMax M3 works** (0G router `router-api.0g.ai/v1/chat/completions`,
  `model=minimax-m3`, Bearer). Emits a `<think>` block -> `max_tokens>=2000`,
  strip before scoring. Verified live this session.
- **`search_twitter` works** (~$0.003/call) and returns real, dated tweets with a
  human-readable summary that already contains the top tweet texts — enough to
  score on without fetching the artifact (artifacts return no body in this harness).
- Note: the shared web/twitter key is **concurrency-limited (2 in flight)** and
  parallel calls can wedge the slot for ~1-2 min — call serially in production.

## Mechanism validation (real historical crash, end-to-end)
Worst 24h drops among the **eligible** universe in the cached 120d panel:
SAHARA -60%, STG -59%, HOME -51%, BARD -47%, ZEC -46%, XPL -29%, APE -28%.

I ran the **exact production pipeline** on the STG crash (-64% peak-to-trough,
Jun 13-14 2026):
- `search_twitter("$STG ... delisting")` -> CoinDesk: *"$STG has slumped ...
  after it was delisted by Coinbase"* (+ Fantom wind-down). A clean, detectable,
  classifiable negative event.
- MiniMax M3 on that text -> `{"negative_event": true, "category": "delisting",
  "severity": 8, "reason": "STG delisted by Coinbase ... severely impacts
  liquidity ... market confidence"}`. severity 8 >= 6 -> **drop to cash.** Correct.

## Timing / asymmetry (the honest, decisive test)
The edge is real but **event-shape dependent**. Veto operates at the 4h
rebalance cadence; assume an ~8h news+decision lag. Remaining drop AVOIDED:

| event (eligible token) | peak->trough | already done @ +8h | AVOIDED by veto |
|---|---|---|---|
| STG (Coinbase delisting) | -64% | -11% | **-60%** |
| HOME | -50% | +22% (pre-bleed) | **-59%** |
| XPL | -32% | -21% | -14% |
| SAHARA (gap dump) | -60% | -55% | -11% |
| ZEC (gap dump) | -45% | -43% | -5% |

- **Staged / announced catastrophes (delisting, regulatory, slow exploit/depeg):
  the veto avoids ~the back -55/-60% of the slide.** This is the win condition.
- **Instant gap-downs (SAHARA, ZEC): news arrives after the gap** — the veto only
  catches the back half (-5 to -11%). It cannot dodge an instantaneous dump, but
  it **never makes things worse** and still trims the tail.

**Convexity, with numbers:**
- Downside if WRONG (false positive): drop one held name for ~1 cycle in cash.
  At top-8 EW (~12.5%/name) the median |4h| move is ~0.66% -> ~0.08% of book +
  ~30bps round trip. Capped, tiny.
- Upside if RIGHT on a staged event: avoid ~-60% of a ~12.5% position ~= **-7.5%
  of total book saved**, and it keeps the worst-name loss well inside the
  contest's 30% disqualification gate.

## Fire rate (rare bet, big payoff)
Severe-crash (`fwd-24h <= -25%`) episodes in 120d:
- Full 64-name eligible universe: 10 names, 14 episodes -> **~0.82 / 7-day window.**
- Realistically-HELD top-12 liquid sleeve: only ZEC, XPL -> **~0.18 / 7d.**

So in a random contest week the veto usually does nothing; when it fires on a
held name it can be decisive. Note ZEC and XPL are *also* top-3 incumbent
holdings — the veto fires exactly where capital is concentrated.

## OOS / cost
A literal walk-forward backtest is impossible (no point-in-time per-token news
archive; LLM scores are non-reproducible) — stated honestly, same constraint the
prior round documented. Validation is therefore an **event study of the
mechanism** on real crashes (above), not a return curve. As a *risk control* it
does not need to beat the ensemble on return: it caps a left tail. Cost is paid
only when it fires (~30bps to exit one name); base rate ~0.18 held-fires/7d makes
the expected drag negligible (<1bp/week of book), and false positives cost ~0.08%
of book each. Sample size is small and honestly so: ~5 catalogued eligible
crashes, 1 fully replayed end-to-end (STG).

## Production veto (clean, bounded, logged) — implemented
`src/bnbhack_agent/news_veto.py` -> `negative_vetoes(client, held_symbols)`:
- **Bounded:** scores only HELD names (<= `max_checks=8`), per-symbol cache with
  `ttl_h=4`, so the LLM/search cost is paid at most ~once/4h/held-name.
- **Best-effort:** every failure path (network, LLM, parse, empty social) returns
  no veto; wrapped in `try/except` in `agent.decide()` so it **never blocks the
  core ensemble decision**.
- **Logged:** returns `(vetoed:set, audit:list[{symbol,severity,category,reason}])`;
  `agent.run_once` writes `news_veto` into the decision record.
- **Merges into the existing `vetoes` set** already threaded through
  `target_weights -> ensemble_weights -> combined_weights` — zero change to the
  frozen strategy math; vetoed names simply get zero weight and the book renorms.
- Wired in `agent.AgentConfig.use_news_veto=True` (toggleable).

## Integrate? YES
Bounded, asymmetric, never blocks core, off-the-hot-path via cache, logged for
audit. It does not chase pumps (that was rejected). Recommend default ON for the
contest window. Caveat to state plainly: it protects against *announced/staged*
catastrophes, not instantaneous gap dumps — but in those it still avoids the back
half and is strictly downside-reducing.
