# Signal Research — Summary of All Tested Hypotheses

Two multi-agent rounds (symmetric + asymmetric) on top of the earlier solo search.
Every hypothesis was held to the same bar: point-in-time (no lookahead), walk-forward
OOS + a locked 21-day holdout, honest about sample size, and **net of ~20–40 bps TWAK
cost** (gas + slippage on spot PancakeSwap). "No edge" is recorded as a real result.

## Verdicts

| Hypothesis | Type | Verdict | Why |
|---|---|---|---|
| Cross-sectional momentum / reversal / vol-concentration | symmetric | ❌ reject | Overfit; collapse OOS (momentum −63%) |
| Time-series momentum, breadth gate/scale, inverse-vol, adaptive sizing | symmetric | ❌ reject | Underperform the regime-gated ensemble OOS |
| On-chain DEX-flow selection / DEX-ignition spikes | microstructure | ❌ reject | MEV/arb adverse selection; mean-reverts; net-negative, fails holdout |
| BSC whale / smart-money copy | on-chain | ❌ reject | Eligible tokens are CEX-priced pegs → on-chain flow decoupled; "whales" are bots; net-buying *precedes worse* returns |
| Funding overheat de-risk / **extreme-negative-funding squeeze-long** | derivatives | ❌ reject | Funding is regime-beta here; squeeze-long bleeds (win 31–43%), holdout decays, single-name (STG) concentration |
| News → allocation tilt (MiniMax M3) | catalyst | ❌ reject | Catalysts are coincident/lagging (M3 itself flags "already priced in"); proxy fails holdout |
| Stablecoin depeg → re-peg | asymmetric | ❌ reject | Premise fails: deep depegs have an **uncapped** left tail (−10% to −33%, recovery > contest window); positive zone fires in only ~6% of weeks on n=4 |
| Token-unlock fade | asymmetric | ❌ reject | No lookahead-free edge beyond regime beta (n=4, one downtrending token); harness blocks broader study |
| CEX listing-announcement pump | asymmetric | ❌ reject | Tradeable in-window events are secondary listings of large caps (flat); genuine convexity lives in untradeable fresh small-caps |
| CMC Fear & Greed euphoria guard | overlay | ✅ **keep** | Do-no-harm, bounded, logged; trims exposure in greed (inert in the current fear regime) |
| Monolit token-security veto | overlay | ✅ **keep** | Cached daily honeypot/tax screen; off the hot path |
| **Negative-news veto (MiniMax M3 + Monolit search_twitter)** | overlay | ✅ **KEEP (integrated)** | Asymmetric risk control: drop a held name on a fresh severe event (hack/exploit/depeg/delisting). Mechanism validated on the STG −64% Coinbase-delisting crash |

## Round 3 (novel angles + sizing)

| Hypothesis | Verdict | Why |
|---|---|---|
| Deep single-token wallet lead-lag (CAKE/ASTER, hourly, full history) | ❌ reject | In-sample "lead" wallets are dormant launch-accumulators (uncopyable) or adverse MM/HFT bots; nothing survives the holdout; multiple-comparison mining over a launch uptrend |
| BTC-breakout alt-catchup | ❌ reject | Fresh BTC new-highs precede alt *under*-performance (local exhaustion); the only positive conditioner is the risk-on MA state the regime gate already harvests; strictly worse OOS than incumbent |
| DEX↔CEX lead-lag (catch arbitragers) | ❌ reject | Lead-lag is real but fully consumed within ~1h; after gas+slippage we are the one front-run |
| MiniMax-M3 moonshot allocator | ⚠️ partial | The LLM doesn't beat the mechanical sleeve OOS; one *feature* it uses (vol-expansion confirm) is a marginally better mover-filter — integrate the feature, not the LLM (optional) |
| **Convex sizing (basket concentration)** | ⚠️ **REVERSED by red-team** | `ensemble_ns=(2,3)`/`cap 0.50` looked like +20% under a flat-10bps assumption, but it ranked by *CEX* volume and concentrated into names with ~no on-chain depth — net of measured PancakeSwap slippage it goes to −40% / 51% DD = **auto-DQ**. Corrected to N=(3,4) over the **DEX-liquid set only**, cap 0.34 (see Round 4). |

## Round 4 (red-team — execution realism)

Five adversarial agents attacked the shipped book on DEX execution, regime whipsaw, concentration
fragility, realistic cost, and adverse scenarios (reports in [`docs/redteam/`](../redteam/)).

| Finding | Verdict | Fix shipped |
|---|---|---|
| **CEX-volume ranking ≠ DEX liquidity** | 🔴 critical | The agent trades on PancakeSwap; CEX volume is irrelevant. The shipped book held names with <$1k/wk on-chain depth → 50%+ slippage DD. **Rank/restrict by measured BSC DEX volume** (`dex_liquid_candidates`); investable set = {ASTER, CAKE, ZEC, XRP, DOGE} (>$20k/wk) |
| **Flat 10bps cost was a phantom** | 🔴 critical | Real per-name slippage is 56–175 bps. Backtest now prices **measured per-name DEX cost + LP fee**; headline is net of it (the +20% was an artifact) |
| Over-concentration (N=(2,3), cap 0.50) | 🟠 | A single-name crash DQ'd the book. **De-concentrated to N=(3,4), cap 0.34** |
| Regime whipsaw bleeds round-trip cost | 🟡 | **Regime hysteresis** (band 0.0075): exit fast, re-enter only above MA×1.0075 |
| Single held-name crash → DQ drawdown | 🟡 | **20% per-name trailing stop** → drop to cash (caps a −50% name from ~38% to ~12% book DD) |
| Dead portfolio drawdown stop (equity hardcoded) | 🟡 | Wired real equity (TWAK live) + all-cash circuit-breaker at the internal hard stop |
| Moonshot churn through thin pools | 🟡 | ~−1.9pp drag under realistic cost → **defaults off** |

## Honest meta-conclusion
Across **~15 distinct hypotheses over three multi-agent rounds** (and many variants), **no robust
return-alpha exists in this universe/period — symmetric or asymmetric.** The "obvious" convex ideas all have a hidden
left tail (depeg), no tradeable edge (listing/unlock), or negative EV (squeeze). The durable
edge remains **regime-gated diversified beta + a capped moonshot sleeve**, and the genuine
value-adds are **bounded risk-control overlays**, not return boosters:
- F&G euphoria guard (CMC), token-security veto (Monolit), and the **negative-news veto** (M3+Monolit).

These also light up all the partner stacks for the prizes (CMC Agent Hub, Trust Wallet
execution, Monolit data, MiniMax M3 via 0G) while being honestly framed as risk control + a
convex moonshot lottery, not fabricated alpha.

## Data-infrastructure learnings (for future work)
- Monolit query results > ~100 rows return as **CSV artifacts with no readable body** in this
  harness → reduce series server-side (`groupArray`/`arrayStringConcat`) or paginate small `LIMIT`.
- Wide on-chain scans without a tight `LIMIT` **time out**; the deriv cluster is concurrency-limited (~2 in-flight).
- Monolit smart-money table has **no BSC coverage**; CMC trending/news endpoints are **plan-gated** on this key.
- On-chain DEX history for the eligible (CEX-listed) universe is **sparse** — only CAKE/ASTER have dense hourly data.
