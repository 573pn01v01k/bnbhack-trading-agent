# Hypothesis: DEX Ignition / Arb Front-Run

**Status: REJECTED — no edge; negative after costs; fails holdout.**

## Hypothesis
On BSC `evm.swap_events`, a sudden spike in DEX swap activity (swap count / unique
senders) on an eligible token reflects arbitrageurs and early flow pushing price, and
should *precede* short-term price continuation. If so, a spike-detection trigger could
feed the capped "moonshot" sleeve.

## Signal (point-in-time, no lookahead)
For a token contract, count DEX swaps per hour from `evm.swap_events` (chain='bsc',
base_coin OR quote_coin = contract). At hour `t` compute a z-score of the swap count vs
the **trailing 168h window, rows t-168..t-1 (current bar EXCLUDED)**:
`z_t = (sw_t - mean(sw_{t-168..t-1})) / std(...)`. Flag ignition when `z_t >= k`.
The window is warmed on pre-period data (query starts a week before the eval window).
Entry is at **t+1** (signal only known at close of `t`); forward return measured
`t+1 -> t+1+h`. Horizons h ∈ {1,4,12,24}h. Forward prices from the cached Binance
hourly panel (the contest's valuation source).

## Data access
Worked, with friction. `evm.swap_events` BSC hourly aggregates pull fine server-side.
Two material constraints:
1. **Artifact wall.** Any result >~100 rows returns as a CSV artifact, and in this
   harness `read_artifact`/`download_artifact` do **not** return the body — so a raw
   2880-row hourly series is unreadable. Workaround: compute the z-score with a
   ClickHouse window function and return only the ignition timestamps as a single
   `arrayStringConcat(groupArray(...))` string (1 row, fully inline).
2. **On-chain coverage is thin for CEX-listed tokens.** Of the liquid eligible set,
   only **CAKE** (avg 27 swaps/h, continuous) and **ASTER** (avg 25/h) have dense,
   continuous hourly DEX series over the 120d window. TWT (~2.8/h), FLOKI (~4.8/h),
   BANANAS31 (42% hour coverage) are too sparse to build a stable spike z-score. A
   cross-sectional moonshot sleeve across the universe is therefore **not feasible** —
   the data only exists for ~2 names.

## Result (forward price return after an ignition bar, %)

Full sample (entry t+1; `mean_net_cost` = gross mean − 40bps round-trip TWAK):

| sym | signal | h | n | gross % | net-cost % | edge vs base % | winrate | t |
|---|---|---|---|---|---|---|---|---|
| CAKE | z≥3 | 1 | 58 | -0.151 | -0.551 | -0.155 | 41% | -1.9 |
| CAKE | z≥3 | 12 | 58 | +0.164 | -0.236 | +0.114 | 47% | 0.6 |
| CAKE | z≥3 | 24 | 58 | +0.001 | -0.399 | -0.103 | 38% | 0.0 |
| CAKE | z2-3 | 12 | 81 | -0.336 | -0.736 | -0.386 | 41% | -1.3 |
| CAKE | z2-3 | 24 | 81 | -0.535 | -0.935 | -0.639 | 37% | -1.6 |
| ASTER | z≥3 | 4 | 103 | -0.198 | -0.598 | -0.193 | 44% | -1.4 |
| ASTER | z≥3 | 24 | 103 | -0.877 | -1.277 | -0.832 | 43% | -2.7 |

Locked holdout (last 21 days), the decisive test:

| sym | signal | h | n | gross % | winrate | t |
|---|---|---|---|---|---|---|
| CAKE | z≥3 | 24 | 14 | -1.092 | 29% | -1.0 |
| CAKE | z2-3 | 24 | 19 | -1.712 | 26% | -2.8 |
| ASTER | z≥3 | 4 | 14 | -1.041 | 14% | -3.4 |
| ASTER | z≥3 | 24 | 14 | -3.158 | 21% | -3.1 |

## Reading
- **Gross forward return after a spike is ~0 to negative** at every horizon; win rates
  sit at/below 50%; t-stats are insignificant except where they are significantly
  *negative*.
- **Edge vs the unconditional baseline is negative** almost everywhere — ignition bars
  underperform simply holding the token. There is no continuation; if anything there is
  mild mean-reversion.
- The lone positive-looking cell (CAKE z≥3, 12h train, edge +0.31%, t=1.1) is
  in-sample only and **inverts to -0.50% in the holdout**. Classic overfit to one window.
- The **holdout is uniformly bad** (ASTER 24h: -3.2%, 21% winrate, t=-3.1). The signal
  does not merely fail to persist — it flips negative out of sample.
- After 40bps round-trip TWAK cost, **every configuration is net-negative**.

## Why (economic interpretation)
For CEX-listed tokens, an on-chain swap-count spike is dominated by **MEV/arb bots
reacting to a CEX price move that already happened** (ASTER's unique-sender count
averages ~3.6 against ~25 swaps/h — heavy bot churn, not organic demand). The
arbitrageurs are not a leading flow we can ride; they are the ones who already moved
price and who front-run our PancakeSwap spot fill. By the time the spike is observable
and we trade via TWAK, we are buying after the move — adverse selection, which is
exactly the negative edge-vs-base we measure.

## Verdict
No edge. The DEX-ignition spike does not predict continuation; it is contemporaneous-to-
lagging arb noise on CEX-listed names, net-negative after TWAK costs, and fails the locked
holdout (negative, significant). It also only has usable data for ~2 of 64 names, so it
cannot power a cross-sectional sleeve. **Do not integrate.** Consistent with the ~25
previously-rejected microstructure/flow signals.
