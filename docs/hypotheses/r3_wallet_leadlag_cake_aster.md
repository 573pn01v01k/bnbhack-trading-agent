# R3 — Deep single-token wallet lead-lag (CAKE & ASTER, BSC on-chain)

**Verdict: REJECTED.** No copyable single-name (or small-cohort) wallet lead exists on either
CAKE or ASTER once the test is made point-in-time and out-of-sample. The only positive results
are artifacts of (1) a noisy on-chain-VWAP return target, (2) multiple-comparison mining over a
one-way launch uptrend, and (3) survivorship — every "informed-looking" wallet is dormant in the
recent / holdout window and therefore literally uncopyable.

## Hypothesis
For the top ~30 wallets by on-chain volume on CAKE and ASTER (the only two BSC-eligible tokens
with dense continuous swap data), does a wallet W's signed net-BUY in hour `t` predict the token's
forward return `t→t+{1,4,12,24}h` beyond baseline? If a wallet or cohort reliably leads price up,
define a point-in-time copy signal and cost it.

## Data & method (point-in-time, no lookahead)
- `evm.swap_events` (chain='bsc'), packed server-side with `groupArray()` into single inline rows;
  parsed locally. Addresses: CAKE `0x0e09...1ce82`, ASTER `0x000a...556a`. Pair = token/USDT
  (`0x55d3...7955`, 18-dec on BSC — the dominant on-chain pool for both).
- **Direction inference.** `swap_events` has NO direction flag; base/quote is canonicalized
  (token is almost always `base`), so orientation does not encode buy vs sell. `transfer_events`
  join returned empty (pool/router legs not captured per-wallet). Used a tick-rule classifier:
  a swap is a BUY if its implied price (`quote_amt/base_amt`) > the hour's VWAP, else a SELL;
  hourly signed net-buy USD per wallet. This is the standard Lee-Ready-style proxy and is the
  honest best available given the schema.
- **Return target.**
  - CAKE: cached **Binance** hourly price (`price_120d.parquet`), 2026-02-16→06-16 — clean CEX
    price, the venue a spot agent trades; fully point-in-time; locked last-21d holdout.
  - ASTER: Binance covers only the recent 120d; the top wallets traded almost entirely during the
    Sep-2025 launch period, so the full-life test had to use a reconstructed on-chain hourly VWAP
    as target. **This target is weak: its hourly-return correlation to real Binance price over the
    overlap is only 0.15** — so all ASTER full-life "significance" is discounted heavily.
- Event study per wallet: excess fwd return vs all-hours baseline, one-sample t-test, win-rate.
  Walk-forward split at a locked 21-day holdout; cohort copy-signal (long when any selected wallet
  net-buys, hold k h) tested IS then OOS.

## Results

### ASTER (top-30 wallets, full life Sep-2025→Jun-2026, on-chain VWAP target)
- 23 wallets had ≥10 buy-hours. In-sample k=12/24 excess returns were a **wide bidirectional
  spread**: e.g. `0xee796e9e` +7.7%/+15.7% (p<0.001), `0xa73072ad` +3.9%/+7.0%, `0xccb16263`
  +3.6%/+6.6% — but `0x27fcc867` −3.8%/−4.9%, `0x0c7c4cbd` −3.5%/−5.5% etc. Across 23 wallets ×
  4 horizons (~92 tests) this is consistent with mining noise over a launch-period uptrend
  (baseline fwd returns were positive by construction: buy-during-the-pump "predicts" the pump).
- **IS-selected winners (k24 exc >1%, p<0.05): 7 wallets. ALL have n=0 buy-hours in the 21-day
  holdout AND n=0 in the entire Binance window.** They went dormant after launch. The cohort
  copy-signal looked spectacular IS (k24 +4.78% excess, p<0.001, n=432) but is **untestable OOS
  (n=0)** — the canonical lead-lag trap.
- Only **2 of 30** wallets are still active recently. Re-tested on the **clean Binance** target:
  - `0xf7abc...` (67k trades, HFT/MM bot): buys **negatively** predict — k24 −0.58% excess,
    p<0.001. Adverse, not a long signal.
  - `0xa27c9867...`: no edge, all p>0.49, win-rate ≈ coin-flip.

### CAKE (top-30 wallets, 120d, clean Binance target — fully point-in-time)
- 9 wallets with ≥15 buy-hours. The one continuously-active wallet `0x9cad0ed0` (595 buy-hrs,
  MM/bot): zero edge IS (p>0.6), **negative OOS** (k24 −0.62%).
- Only **1 of 9** wallets is IS-significant-positive at k24 (`0x4b53acf1` +1.28%, p=0.02) — at the
  ~1/20 false-positive rate expected from the multiple tests — and it has **n=0 in the holdout**.
  `0x2b61256e` (+1.16%, p=0.11) likewise n=0 OOS. Same dormancy/survivorship trap.
- **No wallet active during the holdout shows a positive lead.**

## Why it fails (mechanism)
1. **Survivorship / dormancy.** High-volume single-name wallets are launch-era accumulators or
   distributors. By the time you can identify them, they've stopped trading — you can't copy a
   silent wallet. The wallets that ARE continuously active are MMs/HFT bots whose net-buy is
   adverse (they buy into strength and get mean-reverted).
2. **Target noise on ASTER.** The on-chain VWAP needed for the launch window correlates only 0.15
   with real price; on the clean CAKE/Binance test (no such excuse) the edge vanishes outright.
3. **Multiple comparisons over a trending sample.** 23-30 wallets × 4 horizons with a positive
   baseline drift manufactures both large positive and large negative "edges"; none replicate OOS.

## Copy signal (defined, then killed by cost + OOS)
Signal: at hour `t`, if a pre-identified informed wallet's tick-rule net-buy USD > 0, go long the
token, hold k h. Even before cost, **no formulation survived the 21-day holdout on either token**
(winners n=0 OOS; active wallets flat-to-negative). With ~20-40 bps round-trip PancakeSwap TWAK
cost on top, the only OOS-testable active signals (the MM bots) are net-negative. Nothing to ship.

## Disposition
Do NOT integrate. This closes the user's top-priority "do it properly" wallet lead-lag ask on the
two densest BSC names: a copyable single-name lead does **not** exist. Reinforces the standing
meta-finding (edge = regime-gated beta + capped moonshot, not selection alpha). If revisited, the
only non-dead angle would be a *live* MM-inventory fade (short-horizon mean-reversion against the
active MM bot's net-buy), but that is a different (intraday, short, capacity-tiny) hypothesis and
the active-wallet k24 signs here are too weak/!inconsistent to motivate it.
