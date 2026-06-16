# BNB Hack: AI Trading Agent Edition — extracted rules and fit

Sources checked on 2026-06-05: CoinMarketCap hackathon page, BNB Chain hackathon page, CMC API docs, Trust Wallet portal, BNB Agent SDK README.

## Hard facts

- Event: **BNB Hack: AI Trading Agent Edition**, CoinMarketCap × Trust Wallet × BNB Chain.
- Build window / DoraHacks registration: **June 3–21, 2026**.
- CMC page says submission lock is **June 21 · 12:00 UTC**.
- Prize pool: **$36,000**.
- Two tracks:
  - Track 1: Autonomous Trading Agents — live BSC trading via CMC + TWAK + BNB AI Agent SDK, scored on real PnL.
  - Track 2: Strategy Skills — CMC Skill generating trading strategies from market data; deliverable is a **backtestable strategy spec**, not a live agent.
- Required: use **at least one sponsor capability**.
- Recommended / judging edge: stack all three — **CMC for signal, Trust Wallet Agent Kit for execution, BNB Chain for venue**.
- FAQ: PnL replay runs against held-out market window after submission lock; judges score returns, drawdown, risk-adjusted performance, and rule adherence.
- FAQ: one team may submit to multiple tracks, but each submission needs its own working agent; most winning teams focus on one track.
- FAQ: special prizes stack with main prizes.
- FAQ: support via Builder Telegram + weekly mentor office hours.
- DoraHacks snippet: GitHub/GitLab/Bitbucket link required.

## Sponsor capabilities relevant to this repo

- CMC Agent Hub / Data API / Data MCP:
  - Market quotes, global metrics, technicals, on-chain metrics, derivatives, sentiment/news, trending narratives.
  - API auth via `X-CMC_PRO_API_KEY`.
  - MCP endpoint: `https://mcp.coinmarketcap.com/mcp` with `X-CMC-MCP-API-KEY`.
  - x402 optional endpoint for pay-per-request data access.
- Trust Wallet Agent Kit (TWAK): CLI + MCP server; examples include `twak serve`, `twak price ETH`, `twak swap 100 USDC ETH --quote-only`, `twak wallet portfolio`.
- BNB AI Agent SDK: Python package `bnbagent` for ERC-8004 identity and ERC-8183 agentic commerce; not required for Track 2 but useful for Track 1/special prize extensions.

## Monolit MCP / external data policy

The public rules say at least one sponsor capability is required and all-three sponsor usage is favored. They do **not** say external/private data sources are forbidden. This repo therefore treats Monolit MCP as optional alpha enrichment only: CMC remains the required primary data/signal layer, and the agent works without Monolit.
