# CEX Listing-Announcement Pump — REJECTED (universe mismatch)

## Hypothesis
A fresh CEX listing announcement is a convex pump catalyst: enter at/after the
announcement timestamp, capture a large forward spike, capped downside.

## Data
- `cex.listings` (Monolit MCP): announcements only, 3 cols (cex_name, ticker, dt),
  2023+, ~12.9K rows, 20 exchanges. ANNOUNCEMENTS not confirmed listings.
- Pricing off cached Binance hourly panel `price_120d.parquet`
  (68 symbols, 2026-02-16 16:00 → 2026-06-16 15:00 UTC, point-in-time).

## The killer: universe mismatch (this is the whole story)
The convex pump lives in *fresh first-ever* listings of small tokens. The agent
trades large/mid-cap spot names that are ALREADY listed everywhere.

- 48 tokens received their first-ever listing announcement in the 120d window (~2.8/wk).
- Of those 48, only **2** are in the eligible tradeable universe (BSB, SNX),
  and only **1** (SNX) has price data in the panel.
- The other 46 (LOBSTAR, CAPTCHA, BLINKY, MONSTRO, 龙虾, TSLAX, ...) are small
  tokens we can neither price nor trade on our spot PancakeSwap book.
- For panel symbols, the only in-window announcements are SECONDARY listings of
  already-global names: NIGHT@Binance, SNX@Robinhood, XAUT@Binance.

So the catalyst with convexity is structurally untradeable for this agent, and the
catalyst that IS tradeable (secondary listing of a large cap) carries no convexity.

## Event study (n=3, the only tradeable in-window events)
Entry = first hourly bar strictly after the announcement (no lookahead).
Returns net of 30bps round-trip TWAK cost.

| token | cex       | +1h  | +4h  | +12h | +24h | +72h | +168h |
|-------|-----------|------|------|------|------|------|-------|
| NIGHT | Binance   | -3.2 | +1.8 | +0.0 | +0.5 | +3.6 | -0.3  |
| SNX   | Robinhood | -0.6 | -0.9 | -3.5 | -2.8 | -0.6 | -2.2  |
| XAUT  | Binance   | -0.9 | -1.8 | -1.1 | +0.5 | +0.4 | +3.9  |

Mean net forward return: +1h -1.6%, +4h -0.3%, +24h -0.6%, +72h +1.1%, +168h +0.5%.
Max single-event 7d move = +3.9% (XAUT — that is gold drift, not a pump).
No event produced anything resembling a 20-50%+ moonshot. Announcement bar drifts
slightly negative intraday.

## Asymmetry
Not convex on the tradeable set. Upside-when-fired is single-digit % (a large cap
does not 2x on getting added to one more venue); downside is uncapped beta the same
as any other hold; and every entry pays 20-40bps. Convexity exists in fresh small-cap
first-listings but that population is outside both the price panel and the eligible
PancakeSwap universe.

## Fires per week
On the tradeable panel: ~0.18/wk (3 events in 17.3 weeks), and those are all
no-pump secondary listings. Genuinely convex fresh-listing events: ~2.8/wk in the
broad market but ~0/wk for symbols this agent can actually buy.

## Verdict: REJECT
Right intuition, wrong universe. The listing-pump edge is real in crypto but it is
priced into small fresh tokens we cannot trade or price here. For our large/mid-cap
spot book a listing announcement is a secondary event with no measurable convexity
and negative expectancy after cost. Do not integrate.

## If you wanted to revive it (out of scope now)
Would require: (1) trading the fresh-listing tokens themselves on-chain at TGE via
`query_evm_onchain`/DEX, with strict size caps and rug/security screening
(`get_token_security`), and (2) a price source for those names (DEX swap VWAP, not
the Binance panel). That is a different agent (new-token DEX sniping), not this one.
