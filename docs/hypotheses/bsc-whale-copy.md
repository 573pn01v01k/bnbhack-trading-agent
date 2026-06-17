# Hypothesis: BSC Whale / Smart-Money Copy

**Date:** 2026-06-17
**Verdict: NO EDGE. Do not integrate.** The signal is uninformative-to-mildly-perverse;
the data is structurally unfit; this is a finer-grained re-run of the already-rejected
"on-chain DEX-flow selection" hypothesis.

## Hypothesis
Find BSC wallets that reliably PRECEDE upward moves on liquid eligible BEP-20 tokens.
Rank wallets by net accumulation, then test whether, in the hours/days after a
top-wallet net-buy, the token's forward return is positive beyond baseline. Build a
point-in-time copy signal (buy when tracked wallets accumulate) and cost it at ~20 bps.

## Data pulled (Monolit MCP, `evm.swap_events`, chain='bsc')
- 6 tokens with real BSC DEX activity, resolved from the universe by liquidity:
  ZEC, XRP, ADA, DOGE, UNI, LINK (contracts in `scripts/_whale_copy_study.py`).
- ETH-peg contract had **12 swaps in 30 days** — effectively no on-chain market; dropped.
- Daily net-buy (token units) per token, computed server-side via `groupArray`, **2026-05-17 → 2026-06-17** (~32 days).

### Structural problems found while pulling
1. **History is ~30 days only.** `swap_events` for these BSC contracts starts 2026-05-18,
   vs the 120-day price panel. A walk-forward with a 21-day holdout leaves ~9 days of
   train — no honest OOS is possible. Daily resolution gives ~32 points/token.
2. **These are Binance-peg / bridge tokens.** Price is set on global CEX, not BSC DEX.
   On-chain flow is a tiny lagging shadow, not price discovery.
3. **The active wallets are bots, not informed money.** Top wallets by count are MEV/arb
   round-trippers (e.g. one wallet 2,140 buys / 0 sells; many buy≈sell roundtrips).
   Monolit has no BSC smart-money table, and hand-rolled accumulator ranking just surfaces
   these bots. Median ~3 unique wallets/hour — far too thin to "copy."

## Signal definition (point-in-time, no lookahead)
For day d: `net_buy(token, d)` = Σ(token received as quote) − Σ(token spent as base) over
all BSC swaps with `block_time` in day d. Signal known at end of d. Return earned is the
Binance-spot close-to-close return **d → d+1** (the contest's USD valuation source). Copy
strategy: hold equal-weight the tokens with `net_buy(d) > 0`, rebalanced daily, 20 bps/side
turnover cost.

## Event study (next-day return conditioned on sign of net-buy)

| metric | value |
|---|---|
| Pooled corr(sign(net-buy), next-day ret) | **−0.156** (n=180) |
| Pooled corr(net-buy, next-day ret) | 0.004 |
| Contemporaneous corr(net-buy, same-day ret) | **0.031** |
| E[ret \| net-buy day] | **−1.14%** |
| E[ret \| net-sell day] | +0.44% |
| E[ret \| all] | −0.48% |
| E[ret \| strongest-accumulation (z top 25%)] | **−1.39%** (worse than baseline) |

The flow does not even track the **same-day** price (corr 0.03) — confirming it carries
essentially no price information on these peg tokens. Where it predicts at all, net-buying
PRECEDES *worse* returns (buyers chase / arb closes a gap that reverts).

## Backtest (OOS / holdout)
- Naive long-only copy (20 bps cost): **−30.5%** over 32 days vs equal-weight 6-token
  buy&hold **−15.2%**. Avg daily turnover 1.11 → ~22 bps/day cost drag alone.
- Locked last-7-day holdout: copy **+4.7%** vs buy&hold **+8.6%** — still underperforms beta.
- Train (25d) buy-minus-sell spread −1.5%/day, holdout spread −1.4%/day — consistently
  negative, no window where copying helps.

## Verdict
No copyable wallet edge on any allowed token. The signal is uninformative at best and
mildly perverse at worst, before costs; after 20 bps and turnover it is strongly negative.
It does not beat — it badly trails — regime-gated beta. The incumbent `ensemble_conc` holds.

Root cause is structural and not fixable with more tuning: (a) the eligible liquid tokens
are CEX-priced peg assets whose BSC DEX flow is decoupled from price; (b) on-chain history
is too short for an honest walk-forward; (c) the wallet population is MEV/arb bots, not
informed accumulators (Monolit has no BSC smart-money coverage to lean on).
