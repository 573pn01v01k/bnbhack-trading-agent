# Red-team Attack #1 — Live DEX execution / slippage reality

**Target:** shipped ensemble book (regime-gated EW, `ensemble_ns=(2,3)`, `max_weight=0.50`,
MAs 240/336/480, 4h rebalance, +10% moonshot sleeve). Backtest assumes Binance hourly price
+ flat 10bps (`StrategyConfig.cost_bps=10`; prompt quoted 30bps). Execution is LIVE SPOT on
PancakeSwap/BSC via TWAK. Capital ~$500. Contest = one random 7-day window, DD>=30% = DQ.

## What the book actually holds
`combined_weights` concentrates into the top-N=2/3 **Binance-CEX-volume** ranked eligible names.
With the live panel + `liquidity.json`, that is:

- Main ensemble nonzero set: `ETH, ZEC, XRP` dominate (top-2/3); pool extends to
  `ADA, BCH, DOGE, INJ, TON, TRX, UNI, XAUT, XPL`.
- Moonshot sleeve rotates over **all 65 eligible names**.

The ranking is by **CEX** volume, but we execute on **BSC DEX**. On BSC these are mostly
Binance-Peg bridged tokens with little native DEX liquidity. (Side bug: universe resolves "ETH"
to `0x4db5a…` = WETH, not Binance-Peg ETH `0x2170…`; both route to the same liquidity so the
volume read is unaffected, but the resolver is picking a non-canonical contract.)

## Measured BSC DEX tradability (Monolit `evm.swap_events`, chain='bsc')

Hourly USD DEX volume (stable/WBNB-leg) and **price impact for a ~$200 order**, measured as the
median absolute deviation of each swap's implied price from its same-hour VWAP (this isolates
impact from price drift; LP fee of ~25bps is additive on top):

| Name | role | DEX $/hr | impact@$200 (med) | impact@$200 (p90) | verdict |
|------|------|---------:|-----:|-----:|------|
| CAKE | (dense benchmark) | ~7k | 34 bps | 90 bps | tradable |
| ASTER | (dense benchmark) | 2.9k | 31 bps | 131 bps | tradable |
| ETH | top-2/3 held | 10.2k | 34 bps | — | tradable |
| XRP | top-2/3 held | 1.2k | 36 bps | 72 bps | tradable |
| ADA | held | 0.5k | 33 bps | 260 bps | marginal |
| **ZEC** | **top-2 held (≈50% wt)** | **2.7k** | **122 bps** | **445 bps** | **expensive** |
| UNI | held | 55 | 87 bps | 476 bps | thin |
| INJ | held | 15 | low-sample | — | untradeable@size |
| XPL | held | 167 | no $200 samples | — | untradeable@size |
| TRX | held | 36 | 18 swaps/14d | — | untradeable |
| BCH | held | 21 | 35 swaps/14d | — | untradeable |
| DOGE | held | 386 | ~150 bps est | — | thin |
| TON, XAUT | held | **no BSC contract** | n/a | n/a | **0 DEX liquidity** |

Tax/honeypot is NOT the problem for the core names: ETH/ZEC/XRP all show 0% buy/sell tax, no
honeypot (ZEC `verdict=low/trusted`, WETH `caution:proxy` only). The problem is pure **depth**.

Worst offender: **ZEC carries up to the 50% per-name cap in the binding 2-name sleeve yet costs
~120bps one-way (p90 445bps)** — the most-weighted held name is among the least tradable.

## Cost sensitivity of the book (full 120d window, `combined_weights`)
One-sided **weekly turnover = 3.63** for the full book; the **moonshot sleeve alone has weekly
turnover 42.68 across all 65 names** within its 10% sleeve (a slippage bomb routing through dead
pools like TON/XAUT).

Flat-cost stress of the shipped book:

| cost | full-window return | maxDD |
|-----:|-----:|-----:|
| 10 bps (frozen) | **+14.6%** | 19.1% |
| 30 bps (prompt) | +1.2% | 22.3% |
| 80 bps | −25.9% | **32.2% (DQ)** |
| 150 bps | −52.2% | 52.7% |

The entire +14.6% edge lives between 10 and ~30bps. Realistic BSC round-trip cost on the held
names is 60–300bps, well into the DQ zone.

## Realized-PnL impact, per-name realistic cost vector
Cost vector = measured impact + 25bps LP fee, applied per name to one-sided turnover; thin/no-pool
names defaulted to 325bps. Holdout = last 21 days (504 bars).

| config | REAL full | maxDD | REAL holdout-21d | maxDD | wk turnover |
|--------|-----:|-----:|-----:|-----:|-----:|
| **CURRENT** (top-12 main, moon=all 65) | **−72.3%** | 72.5% | **−33.6%** | **33.3% (DQ)** | — |
| FIX: filter MAIN only | −75.6% | 76% | −34.4% | 33.9% (DQ) | — |
| FIX: filter MAIN + MOON to DEX-liquid | −30.2% | 33.3% | −6.4% | 7.2% | 3.12 |
| + 12h rebalance | −23.6% | 27% | −2.7% | 5% | 1.85 |
| + 24h rebalance | −19.7% | 24% | −3.0% | 5% | 1.16 |
| + 24h rebalance, **NO moonshot** | −17.9% | 23% | −2.3% | 5% | 0.91 |
| + 12h rebalance, NO moonshot | −18.6% | 22% | **−0.0%** | 5% | 1.24 |
| + 4h rebalance, **NO moonshot** | −17.4% | 22% | **+0.4%** | 4% | 1.71 |

## Conclusion
Under realistic BSC DEX slippage the shipped book is **−72% full-window / −33.6% on the holdout =
disqualified** (DD>30%), versus the +14.6% the 10bps backtest reports. The single biggest sink is
the moonshot sleeve churning 42.68x/week through ~65 names, most of which have little or no DEX
liquidity (TON/XAUT have no BSC pool at all). The main sleeve also over-weights ZEC (~120bps) and
holds several untradeable names (TRX/BCH/INJ).

**Fix (point-in-time, no lookahead):** add a **DEX-liquidity universe filter** applied to BOTH
sleeves, keeping only names with measured on-chain depth (≥ ~$500/hr DEX volume AND ≤ ~50bps
median impact at $200) — i.e. drop to roughly `{ETH, XRP, CAKE, ASTER, ADA}` and exclude any name
with no BSC contract. Combined with removing the moonshot sleeve (or restricting it to the same
liquid set) this takes the realistic-cost holdout from **−33.6% (DQ) to ≈ breakeven (−0% to +0.4%),
maxDD 22% → 4–5%** — converting a guaranteed disqualification into a survivable book.

The filter is computable point-in-time from a pre-contest Monolit `evm.swap_events` scan (14–30d
trailing depth/impact per candidate); it uses only data available before the window opens.

**Honest caveat:** even fully fixed, the book is ~breakeven net of realistic cost — the +14.6%
"edge" was an artifact of the 10bps assumption, not durable alpha. The value here is **blow-up
protection** (avoiding the 30% DQ), not return enhancement. Sample is one 120d panel with a single
21d holdout; the cost vector is a measured-impact estimate, not live TWAK fills.
