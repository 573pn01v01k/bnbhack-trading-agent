# Attack #4 — Realistic-Cost Re-Validation of the Convex N=(2,3) Book

**Verdict: the convex-sizing decision REVERSES under realistic, on-chain-informed BSC DEX cost.**
The shipped concentration is ranked by the *wrong* liquidity signal (Binance CEX 24h volume), so it
concentrates into names that are essentially untradeable on PancakeSwap. Fix = rank by measured BSC DEX
depth and drop DEX-dead names. This is point-in-time and turns a -40% / DQ book into ~breakeven / DQ-safe.

## The weakness

The backtest costs every trade at a flat 10–30 bps. Execution is LIVE on PancakeSwap/BSC DEX. The
`liquid_candidates`/ranking used by the ensemble is **Binance CEX 24h quote volume**
(`universe.liquidity_ranking`), not on-chain depth. Those are different orderings.

The N=(2,3) ensemble (max_weight 0.50) therefore holds, in rank order:

| sleeve | holdings (CEX-rank) |
|---|---|
| N=2 | **ETH, ZEC** |
| N=3 | ETH, ZEC, XRP |

Measured BSC DEX volume, last 7 days (Monolit `evm.swap_events`, stable/major-quote legs):

| token | 7d DEX $vol | swaps | note |
|---|---:|---:|---|
| ASTER | 391,521 | 1506 | dense |
| CAKE | 158,136 | 1823 | dense |
| ZEC | 106,907 | 406 | ok |
| XRP | 64,863 | 672 | ok |
| DOGE | 28,811 | 350 | mid |
| UNI | 3,369 | 58 | thin |
| LINK | 2,153 | 67 | thin |
| ADA | 1,250 | 46 | thin |
| INJ | 1,012 | 15 | thin |
| BCH | 133 | 8 | dead |
| **ETH** | **152** | **2** | **dead** |

The **largest holding of the N=2 sleeve (ETH, capped at 50% = ~$250 of $500) traded ~$152 on BSC DEX
in an entire week (2 swaps).** A single rebalance into it is ~10x the weekly on-chain volume — it is not
tradeable on the venue the agent actually executes on. The convex book systematically rotates the most
weight into the least DEX-liquid names because CEX volume rank ≠ DEX depth rank.

## Quantification (two independent cost models, both anchored to the measured DEX volume above)

**Tiered-step model** (for a ~$250 max single-name trade): dense >$100k/wk = 35 bps, mid $20–100k = 90,
thin $2–20k = 250, dead <$2k = 450. No buy/sell tax on any held name (`get_token_security`: ETH/ZEC taxes 0).

Full 120d window, realistic tiered cost:

| book | full 120d | 21d holdout | 7d-tail mean / P(>15%) / P(<-15%) |
|---|---|---|---|
| **N=(2,3) SHIPPED (CEX-rank)** | **-56.1% dd56%** | **-13.3% dd15%** | -3.9% / 8% / 9% |
| N=(3,5,8) | -57.4% dd57% | -12.7% dd14% | — |
| N=(5,10,15) | -60.8% dd61% | -13.2% dd15% | — |
| equal-weight | -9.5% dd21% | +0.2% dd3% | -0.3% / 0% / 0% |

Even at a *flat* cost, EW beats N=(2,3) from 5 bps upward on this window (concentration's mean-return edge
was already marginal; the claimed value was the right tail). The DEX-depth cost destroys the concentrated book.

## The fix (point-in-time, no lookahead)

**Rank candidates by measured BSC DEX volume, not Binance CEX volume, and restrict the investable set to
names with real on-chain depth (>$20k/wk): {ASTER, CAKE, ZEC, XRP, DOGE}. Loosen concentration to N=(3,4).**

DEX volume is observable at decision time from `evm.swap_events` over a trailing window — no lookahead.
This is the same data the agent already calls Monolit for (flow tilt / security veto).

Walk-forward, 14 stitched non-overlapping 7d OOS windows (21d burn-in), realistic tiered cost:

| book | stitched OOS | max DD | windows positive |
|---|---|---|---|
| **SHIPPED N=(2,3) CEX-rank** | **-40.2%** | **51% (DQ)** | 5/14 |
| **FIX N=(3,4) DEX-rank** | **+2.3%** | **23% (DQ-safe)** | 6/14 |
| FIX N=(2,3) DEX-rank | -7.4% | 22% (DQ-safe) | 6/14 |

Locked 21d holdout, realistic cost: SHIPPED -13.3% (dd15%) → FIX N=(3,4) -2.2% (dd6%).
The winning right tail is preserved: FIX N=(3,4) still posts +12%, +10%, +7% weeks (P(7d>15%)≈4%) with
**zero** sub-(-15%) weeks, whereas SHIPPED's +14% weeks come paired with -18%/-15% weeks and a DQ-level 51% drawdown.

N=(3,4) beats N=(2,3) even inside the DEX-ranked set: the 50% cap dumps too much turnover/impact into a
single thin name (ASTER), so a touch more diversification across the 5 dense names both raises return and cuts DD.

## Honest caveats (sample size)

- One 120d panel, one regime (chop/mild-down for these 5 names) → all active books are net-negative or
  ~flat in absolute terms after realistic cost. The fix's value is **bleed reduction and DQ avoidance**
  (-40%/DQ → +2%/safe), not a positive-return guarantee. That is exactly the kind of realized-PnL
  protection the brief asks for.
- DEX volume measured over the most recent 7d only; depth is regime-dependent and the contest window is
  random. The fix should use a trailing DEX-volume rank refreshed live, not the static snapshot here.
- Square-root-impact coefficient is calibrated, not exact; the tiered-step model is the conservative
  cross-check and both agree on direction and on the crossover (EW/diversified > concentrated at any
  realistic cost).
- Cost-aware optimal concentration on this evidence: **N≈(3,4) over a DEX-depth-filtered set of ~5 names**,
  keeping max_weight ≤ ~0.40 to avoid single-name impact. Do NOT collapse to full equal-weight (P(week>15%)=0
  → can't win a %-ranked leaderboard) and do NOT keep N=(2,3) on CEX rank (bleeds, DQ-prone).
