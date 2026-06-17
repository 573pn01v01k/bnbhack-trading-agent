# Red-team #5 — Adverse-scenario stress test

Attack: simulate the worst weeks and verify the agent's protections actually hold. Quantify worst-case
drawdown under (a) held-token -50% intraweek crash, (b) stablecoin depeg, (c) broad flash crash, (d)
the >=1-trade/day rule in a frozen week. Find the unhandled mode and the minimal point-in-time fix.

All numbers from `src/bnbhack_agent/data/cache/price_120d.parquet` (2880 hourly bars, 68 tokens,
2026-02-16..06-16), the live strategy path `strategy.combined_weights` (FROZEN config), and
`portfolio.strategy_returns` accounting (shift(1) no-lookahead, 10bps/side cost).

## The book is dangerously concentrated in two volatile names
Ranked liquid candidates (top-12): `ETH, ZEC, XRP, DOGE, XAUT, UNI, ADA, TRX, XPL, BCH, INJ, TON`.
With `ensemble_ns=(2,3)` + `max_weight=0.50`, the actual live book averages:

    ZEC 24.9% | ETH 24.4% | XRP 9.8% | (rest <1%)   avg total exposure 62.6%, single-name max 41.7%

ZEC is on the doc's own crash list (negative-news-veto.md: "ZEC -46%"). The largest single holding is
one of the universe's most crash-prone names.

## Scenario results

### (a) Held token crashes -50% intraweek — UNHANDLED by the regime gate
The BTC-keyed regime gate (`regime_off`) cannot see an idiosyncratic single-name crash. Injecting a
realistic -50%/12h slide into a HELD name during a risk-on week (BTC flat, gate stays ON):

    crash ZEC -50%/12h, NO veto:  week DD = 28.6%, week ret = -18.4%   (baseline week +12.6%)
    crash ETH -50%/12h, NO veto:  week DD = 29.5%, week ret = -19.2%
    crash ZEC -65%/18h (STG-like): week DD = 38.2%  -> BREACHES the 30% DQ gate

The news veto is the ONLY defense, and its cadence is the whole story:

    veto +8h (current ~8h news lag + 4h cadence): DD 28.6% -> 19.7%
    veto +4h (tighter cadence):                    DD 28.6% -> 12.0%

So at the documented ~8h lag, a single held-name crash still parks the book at ~20-30% DD — within a
hair of (or past) the DQ line. The veto also depends on social/LLM availability (best-effort, can return
nothing) and only catches *narrative* crashes; a pure gap-down with no Twitter chatter is missed.

### (b) Stablecoin depeg — out of the backtest, real only at live routing
There is no stablecoin column in the price panel; "risk-off" = flat USD (0% exposure). So a depeg cannot
show up in the validated backtest at all. The real exposure is live-only: every TWAK swap routes through
USDT and the heartbeat rotates USDT<->USDC (agent.py:205). A held stable leg that depegs is invisible to
the strategy and to the BTC regime gate. Not quantifiable here, but it is an unmodeled live tail.

### (c) Broad flash crash (all alts -30%/4h incl. BTC) — HANDLED WELL
A -30%/4h move in BTC instantly breaks even the slow 480h MA, so all three ensemble regime MAs flip
risk-off at lag 0. The regime mask is applied AFTER the 4h ffill in `target_weights`, so exposure zeroes
at the crash bar with no cadence lag:

    broad -30%/4h flash crash: week DD = 11.3%, week ret = -4.5%   (well under the 30% gate)

The regime gate is genuinely protective for SYSTEMIC crashes. The hole is purely idiosyncratic (a).

### (d) >=1 trade/day in a frozen week — fires, but with ZERO margin
The main ensemble book has turnover gaps up to 476h (20 days) with no trade; 7 stretches exceed 20h.
The moonshot sleeve trades in 90.8% of risk-off bars, but the longest fully-flat run is exactly 20h ==
`heartbeat_hours=20`. The heartbeat fires just in time, but: (i) it has no safety margin, (ii) it depends
entirely on the cron actually running each cycle and on `last_trade_ts` persisting in state.json. A
missed cron cycle or a state reset during a frozen week can silently drop a trading day -> DQ.

## Two structural defects found

1. **The `hard_drawdown_stop` (0.22) is effectively dead code in the model path.** In `agent.py:173`
   `current_equity = config.capital_usd` is hardcoded, so `drawdown` is always 0.0 and
   `check_trade_allowed` never trips the stop unless live TWAK equity is wired in. Even live, the gate
   only BLOCKS NEW BUYS — it never liquidates an existing held position that is bleeding. The validated
   backtest (`portfolio.simulate`) has NO drawdown stop at all. So "the regime gate holds the worst
   drawdown under the 30% gate" is true only for systemic crashes; the documented DD protection does not
   exist for an idiosyncratic held-name crash.

2. **No per-name intra-week stop.** The book has nothing between "hold full weight" and "BTC regime
   flips" — exactly the gap a single-token crash falls through.

## Minimal fix — point-in-time per-name trailing stop on the held book

Add a per-name trailing stop to `combined_weights`/the live held set: if a held name is >=20% below its
trailing-24h peak (computed from past prices only — no lookahead), force its weight to 0 on the next bar
until a rebalance re-initiates it. This backstops the news veto for gap/idiosyncratic crashes that the
BTC gate and the social-LLM veto miss.

### Validation (net of 10bps/side cost)

Insurance value, on the injected crashes (regime gate inert):

    ZEC -50%/12h:  DD 28.6% -> 12.0%,  week ret -18.4% -> +0.6%
    ETH -50%/12h:  DD 29.5% -> 15.0%,  week ret -19.2% -> -2.5%
    ZEC -65%/18h:  DD 38.2% (DQ) -> 12.6%,  ret -29.5% -> -0.1%   <- converts a DQ into a survivable week

Carry cost on REAL history (honest): the stop almost never fires, because the real -50/-65% crashes in
this window (STG/SAHARA/HOME) were never in the top-2/3 liquid book. So it is near-free, not alpha:

    full 120d:   BASE +14.59% / DD 19.1% / Sh 1.07   vs   FIX(20%) +14.52% / DD 19.1% / Sh 1.06
    holdout 21d: BASE  +1.49% / DD  5.3%             vs   FIX(20%)  +1.41% / DD  5.3%
    4x 30d folds: returns/DD identical to base to within 0.1pp (stop never fires)

So the fix costs ~0.07% over 120d and is invisible in every walk-forward slice, while capping the
worst-case held-crash week from a DQ breach to ~12% DD. A 15% stop caps even tighter (ZEC -50% -> DD 8.5%)
at slightly more whipsaw risk; 20% is the conservative point.

### Honest caveats
- The crash magnitudes/timing in (a) are INJECTED, not observed in-window — no held name actually crashed
  >20% intraweek in these 120d, so the fix's *protection* is demonstrated on synthetic stress, and its
  *near-zero cost* is demonstrated on real data. That asymmetry is exactly what a cheap tail hedge looks like.
- The stop fires on a 24h trailing peak; a slow grind-down below 20% over >24h would re-arm the peak and
  could escape it. For a sharper guard, also gate on a fixed since-entry reference.
- Fixes #1 (wire live equity into the DD stop + make it liquidate, not just block buys) and the heartbeat
  margin (raise to ~18h trigger / add a cron-missed alarm) are separate, cheaper hardening items.

## Verdict
The regime gate is real protection for systemic/flash crashes (DD ~11%, exits at lag 0). It is WORTHLESS
for an idiosyncratic crash in a held name, which is the most likely DQ event given ZEC is ~25-42% of the
book. The advertised `hard_drawdown_stop` is dead in the model path and only blocks buys when live. The
heartbeat works but with zero margin. The single highest-leverage fix is a point-in-time per-name 20%
trailing stop: it caps the held-crash tail from a 30-38% DQ breach to ~12% at ~0.07% carry cost over 120d,
with no degradation in any OOS fold or the locked 21d holdout.
