# Hypothesis: DEX<->CEX Lead-Lag / Catch-Up

**Status: REJECTED — the lead-lag is real but fully consumed within 1 hour by
arbitrageurs; no residual edge at our executable cadence; net-negative after cost;
fails the locked holdout.**

## Hypothesis
CEX (Binance/Bybit) price leads PancakeSwap DEX price. After a CEX up-move, the implied
DEX price lags and then catches up. A spot PancakeSwap buy placed into that lag should
capture the catch-up move before exiting at the (CEX-referenced) contest valuation.

## Signal (point-in-time, no lookahead)
- Implied DEX price built from `evm.swap_events` (chain='bsc') as hourly VWAP of the
  token/USDT pool: `px_t = sum(usd_amount) / sum(token_amount)` over all swaps in hour
  `t`, handling both swap directions. USDT = `0x55d3…7955` (18 dec on BSC).
  - CAKE pool `0x0e09…ce82`/USDT: 11,387 swaps, dense (1,086 of ~1,128 hours covered).
  - ASTER pool `0x000a…556a`/USDT: dense but sparser (779 hours).
- CEX reference = cached Binance hourly panel (`price_120d.parquet`), the contest's
  valuation source.
- Bad VWAP prints (multi-hop / sandwiched txns) filtered by `|dex/cex − 1| < 8%`
  (keeps 96% CAKE / 100% ASTER of joined hours).
- **Signal at close of hour `t`:** CEX 1h return `≥ up` (0.5% / 1.0%) AND DEX trading at a
  discount to CEX (`dex/cex − 1 ≤ disc`, disc ∈ {0, −0.2%}).
- **Entry: the earliest executable bar = DEX VWAP of `t+1`.** (We cannot fill at the
  hour-`t` VWAP — that price is contemporaneous with the signal and already gone.)
- Exit at CEX price `t+1+h`, h ∈ {1,4,12}h. Net of 40 bps round-trip TWAK.

## Data access
Worked. `evm.swap_events` BSC hourly VWAP packed server-side into ONE inline row via
`arrayStringConcat(groupArray(...))` — the only way past the artifact wall. Same coverage
constraint as prior on-chain rounds: only CAKE and ASTER have dense hourly DEX series
among the eligible CEX-listed universe, so this can never power a cross-sectional sleeve.

## The lead-lag is real…
- `corr(cex_ret[t−1], dex_ret[t])` = **+0.22 (CAKE), +0.32 (ASTER)** — prior-hour CEX
  return predicts current-hour DEX return. The DEX genuinely lags the CEX.
- Contemporaneous `corr(cex_ret[t], dex_ret[t])` = 0.37 / 0.58; the t−2 lag is ~0.
  So the lag is concentrated entirely in the **first hour**.
- A naive sim that enters at the **hour-`t` DEX price** looks spectacular: CAKE 0.5%-up,
  h=1, n=114, gross **+0.58%**, net **+0.18%**, win **75%**, **t=+6.5**. This is the
  "alpha" the hypothesis predicts.

## …but it is not capturable. The catch-up finishes before we can trade.
The naive result is a **lookahead artifact**: it assumes we buy at the lagged price the
instant we observe it. The honest entry is `t+1`'s DEX VWAP, and by then the gap is gone:

| metric | CAKE | ASTER |
|---|---|---|
| mean DEX discount at signal hour `t` | −52.4 bps | −60.5 bps |
| mean DEX discount at executable bar `t+1` | **−1.5 bps** | **+10.1 bps** |
| mean DEX price move `t → t+1` (entry slip) | **+55 bps** | **+60–100 bps** |

The DEX rises ~55-100 bps between the signal and the executable bar — i.e. it converges
to the CEX within the hour. We pay that slip on entry, leaving nothing.

## Result (HONEST FILL: enter at DEX `t+1`, net of 40 bps)

CAKE, best cells:

| up | disc | h | sample | n | gross % | net % | win % | t |
|---|---|---|---|---|---|---|---|---|
| 0.5% | 0 | 1 | full | 109 | +0.04 | −0.36 | 45% | +0.36 |
| 0.5% | −0.2% | 1 | full | 83 | +0.09 | −0.31 | 48% | +0.69 |
| 0.5% | −0.2% | 1 | **holdout** | 55 | +0.23 | **−0.17** | 53% | +1.31 |
| 1.0% | −0.2% | 4 | full | 34 | −0.50 | −0.90 | 38% | −1.70 |

ASTER, representative cells:

| up | disc | h | sample | n | gross % | net % | win % | t |
|---|---|---|---|---|---|---|---|---|
| 0.5% | 0 | 1 | full | 94 | −0.13 | −0.53 | 52% | −0.97 |
| 0.5% | −0.2% | 1 | **holdout** | 31 | −0.30 | −0.70 | 52% | −1.11 |
| 1.0% | 0 | 12 | full | 35 | −1.44 | −1.84 | 31% | −2.97 |

## Reading
- **Every honest-fill configuration is net-negative** after 40 bps. The single
  least-bad cell (CAKE 0.5%/−0.2%/h=1) is gross +0.09% — below cost — and its holdout is
  net −0.17%. ASTER is uniformly negative and significantly so at longer horizons.
- Gross h=1 returns are ~0 because the catch-up is already priced into the entry; longer
  horizons just add directional CAKE/ASTER beta noise (and it was a downtrend).
- The decisive holdout test confirms it: no configuration clears cost out of sample.

## Why (economic interpretation)
The basis std is large (78 bps CAKE / 55 bps ASTER, |basis|>20 bps ~half the hours), so
there *is* a wide, frequently-mispriced DEX<->CEX spread. But it is closed by atomic-block
arbitrageurs and MEV bots within the same hour we first observe it. We are the slow,
TWAK-paced spot taker on PancakeSwap — by construction the one being front-run, not the
one capturing the spread. This is the same adverse-selection result as the DEX-ignition
round (no continuation; we arrive after the move), now shown directly in price space:
the convergence half-life is well under one hour, far inside our minimum execution
latency. Capturing it would require atomic CEX-leg + DEX-leg arbitrage with gas-priority
bidding — not a SPOT TWAK buy, and out of scope.

## Verdict
The lead-lag signal is genuine and statistically strong **in-sample with a lookahead
fill**, which is exactly the trap. Moved to the only executable price (next-hour DEX
VWAP), the edge is fully arbitraged away (discount −52 bps → −1.5 bps in one hour),
net-negative after TWAK cost, and fails the locked 21-day holdout. Also only ~2 of 64
names have the data. **Do not integrate.** Consistent with the meta-finding: no
capturable convex/return-alpha in this universe at our cadence; the microstructure edge
belongs to faster arbitrageurs.
