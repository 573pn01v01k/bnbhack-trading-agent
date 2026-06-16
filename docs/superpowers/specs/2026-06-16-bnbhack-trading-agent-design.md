# BNB Hack Track 1 — Autonomous Self-Custody Trading Agent (Design)

**Date:** 2026-06-16
**Hackathon:** BNB Hack: AI Trading Agent Edition (BNB Chain × CoinMarketCap × Trust Wallet)
**Track:** 1 — Autonomous Trading Agents ($24,000) + Best Use of TWAK special ($2,000)
**Posture:** Flagship agent — competes for the PnL leaderboard AND the Best-Use-of-TWAK panel prize. Craft-first, ≤$500 real capital.

---

## 1. Concept

A self-custodial autonomous trading agent on BSC whose market-read brain runs on a crypto data layer most teams will not have — Monolit's live on-chain BSC flow + CEX derivatives, layered on top of CoinMarketCap's Agent Hub. It reads markets, decides allocation under hard risk rules, and signs/executes every trade itself through the Trust Wallet Agent Kit (TWAK) in unattended self-custody mode. It pays for its market data keyless, per request, via x402.

One agent, three wins targeted (judges explicitly reward using all three stacks):
- **Best Use of TWAK** (panel-judged on craft / self-custody depth / x402 / autonomy) — primary, controllable.
- **PnL leaderboard** (ranked by % return; ≤$500 is not a handicap since ranking is percentage-based with simulated costs) — near-free option.
- **Best Use of Agent Hub** (broad CMC tool use + x402) — secondary.

## 2. Goals / Non-goals

**Goals**
- Genuinely autonomous: runs unattended over the full Jun 22–28 window, signing its own transactions.
- True self-custody: private keys never leave the host; model never touches keys.
- Deep, non-cosmetic integration of all three stacks (TWAK execution + x402, CMC Agent Hub data, BNB SDK identity).
- A defensible market-read edge from Monolit data that competitors using only CMC REST will not have.
- Survive the 30% max-drawdown DQ gate; never blow up.
- Backtested, evidence-driven strategy config — not a vibe.
- Reproducible public repo + clear demo with on-chain proof.

**Non-goals (this MVP)**
- Perpetuals / shorting / leverage (in scope per rules, but deferred to stretch — keeps the build tight and the self-custody story clean for the deadline).
- Multi-wallet "lottery ticket" portfolio (DoraHacks binds one agent address per submission; one clean flagship).
- A general-purpose trading framework. We build exactly what wins this contest.

## 3. The game (what scoring actually rewards) — verified

- Eligible universe: a fixed **149 BEP-20 tokens on CMC** (includes stables USDT/USDC/USD1/FDUSD and BSC names BNB/CAKE/TWT/ASTER…). Trades outside the list don't count.
- Portfolio valued in **USD hour-by-hour**; ranked by **total % return**. Simulated transaction costs apply. Minimum **≥1 trade/day** (7 over the week).
- Must hold a non-zero balance of in-scope assets at start. **Dust rule:** any hour starting with portfolio ≤ $1 counts as 0% that hour (irrelevant at $500; the 30% DD gate triggers first).
- **30% max-drawdown = disqualification.** "Most profit without blowing up."
- The game reduces to: **dynamic long/flat rotation** among the 149 (concentrate into what's about to rise; rotate to listed stables on risk-off). No spot shorting — convexity comes from concentration, not leverage.
- Registration: on-chain `CompetitionRegistry` `0x212c61b9b72c95d95bf29cf032f5e5635629aed5` (BSC). `registrationStart` = 2026-06-02 21:15 UTC, `registrationDeadline` = 2026-06-25 00:00 UTC (owner-settable). **Practical cutoff: register before Jun 22** (trading opens). Plus submit agent address on DoraHacks.

## 4. Architecture (5 layers)

### 4.1 Signal layer — our edge
Monolit MCP (verified BSC coverage):
- **On-chain BSC flow** (the differentiator): `query_evm_onchain` over `evm.{swap_events, transfer_events, defi_events}`, chain='bsc' — 66.5M rows/7d, fresh to minutes. Decimals trap: USDC/USDT=6, WBTC=8, native/WETH=18.
- **CEX derivatives / regime** (Binance covered): `query_cex_normalized` / `query_cex_canonical` / `query_cex_aggregates` — funding, OI, mark, liquidation, hourly taker buy/sell imbalance (`coin_taker`), 1m klines.
- **TA**: `get_and_calc_cex_technical_analysis` (RSI/MACD/BB/levels, Bybit-backed, majors) for listed names; on-chain swap momentum for the long tail.
- **Safety gate**: `get_token_security` (chain='bsc') — drop honeypot / high-tax / unlocked-LP / hidden-owner names before sizing (DD-risk hygiene).
- **Universe resolution**: `query_verified_tokens` (bsc, 6,189) symbol→contract.
- **Social/narrative**: `search_twitter` (~$0.005/call), `search_news`.

CoinMarketCap Agent Hub (12 MCP tools at `https://mcp.coinmarketcap.com/mcp`; `tools/call` needs key OR x402):
- `get_global_crypto_derivatives_metrics` (global OI/funding/squeeze), `get_global_metrics_latest` (fear&greed, altseason, dominance, ETF flows), `trending_crypto_narratives`, `get_crypto_quotes_latest`, `get_crypto_technical_analysis`, `get_crypto_latest_news`, `get_crypto_metrics` (holder distribution), `search_cryptos` (symbol→id), etc.

**Data payment via x402 (keyless):** CMC x402 endpoints at `pro-api.coinmarketcap.com/x402/...`, **USDC on Base (eip155:8453)**, ~$0.01/request. Flow: request → HTTP 402 with base64 `payment-required:` header → sign challenge → resend with `PAYMENT-SIGNATURE` header → 200. The agent pays via `twak x402 request <url>` (TWAK supports Base). This ticks the TWAK "native x402" criterion and the "uses all three stacks" bonus. (At build time, fetch a real 402 to capture the exact challenge schema; confirm whether the MCP host also accepts x402 vs needing a CMC key for non-x402 endpoints.)

### 4.2 Strategy engine (parametric)
Pipeline each decision cycle:
1. **Universe filter:** 149 → drop security-flagged + illiquid (min 24h volume / orderbook spread threshold).
2. **Score** each candidate: weighted blend of `momentum` (multi-TF), `on-chain net-inflow` (defi_events flow into token, trailing window), `taker-skew` (coin_taker buy/sell imbalance), `funding-regime` (funding flip / OI build). Weights are parameters.
3. **Regime gate:** global risk-on/off from CMC fear&greed + cross-venue funding + BTC/BNB taker-skew + liquidation spikes. Risk-off → rotate to listed stables.
4. **Sizing:** barbell — a vol-targeted core basket (survivability) + a concentrated satellite (upside), split is a parameter. Per-token cap.
5. **Risk caps (hard, non-negotiable):** running-drawdown stop well inside 30% (e.g. circuit-break + de-risk at 18–22%), per-trade max loss, daily loss limit, slippage guard, dust-guard, enforce ≥1 trade/day (via `twak automate` heartbeat if no signal fires).

### 4.3 Execution — TWAK self-custody (the heart of the TWAK prize)
- Wallet: `twak` (`@trustwallet/cli`), BIP39 HD, mnemonic AES-256-GCM encrypted in `~/.twak/wallet.json`; password via `TWAK_WALLET_PASSWORD` env / OS keychain.
- Swaps: `twak swap <amt> <from> <to> --chain bsc --slippage <bps>` — real signing op, routed via TWAK's DEX aggregator (PancakeSwap sits behind it). `twak erc20 approve` as needed.
- Cadence / min-trade rule: `twak automate add` (DCA/limit) as scheduled heartbeat.
- Autonomy: `twak serve --watch` (MCP stdio or `--rest`, localhost-only) so the agent signs unattended; password from env/keychain. Keys local; the model orchestrates but never sees keys → "genuinely hands-off self-custody trader," not plumbing on an LLM.

### 4.4 Identity + registration
- `CompetitionRegistry.register()` registers `msg.sender` (deduped per wallet). TWAK exposes **no generic contract-call**, so registration uses our own web3 signer (ethers/web3.py) signing with the agent key — OR the **BNB AI Agent SDK** (`bnbagent-sdk`: ERC-8004 identity + signing) for the on-chain call. This is also where the BNB SDK earns its place in the "all three stacks" story.
- Submit agent address + strategy writeup on DoraHacks. Answer required questions (Telegram contact, agent address).

### 4.5 Backtest / auto-research loop (H4)
- Harness over Monolit historical BSC on-chain + CEX data: replay the strategy engine across rolling 7-day windows, walk-forward.
- Objective: maximize total return subject to max-drawdown < cap; search the parameter space (signal weights, core/satellite split, thresholds, regime sensitivity).
- Selects + freezes the live config; validates edge out-of-sample (guard against overfitting — report in/out-of-sample spread).
- Doubles as a demo artifact (equity curves, DD distribution, ablation of the Monolit signals) that demonstrates rigor to the panel.

## 5. Data flow

```
[Monolit MCP: on-chain BSC flow, CEX deriv, TA, security, social]
[CMC Agent Hub: global regime, narratives, quotes]  ── paid via x402 (twak, USDC/Base)
            │
            ▼
   Signal layer  →  Strategy engine (score→regime→size→risk caps)
            │
            ▼
   TWAK execution (twak swap --chain bsc, serve --watch, automate)  → BSC mainnet
            │
            ▼
   State/PnL log + on-chain tx hashes  → demo + DoraHacks proof
```

Decision cycle cadence: configurable (e.g. every N minutes / hourly), aligned to the hourly valuation, with the automate heartbeat guaranteeing ≥1 trade/day.

## 6. Tech stack (proposed)
- **Python** orchestrator + strategy engine + backtest (pandas/numpy). Best fit for quant + Monolit data.
- **TWAK CLI (node)** shelled out via subprocess for all signing/execution/x402.
- **Monolit** data via its MCP/API (keys from Pavel). **CMC** via x402 (keyless) with API-key fallback.
- **web3.py / bnbagent-sdk** for the one-off registration tx.
- Runs on Pavel's always-on Linux VPS for the live window.

## 7. Capital & wallet setup
- ≤$500 trading capital in BSC (start in a listed stable + a non-zero in-scope asset to be rankable at T0).
- Small USDC on **Base** to fund x402 data payments (cents).
- BNB for gas.

## 8. Scope
- **MVP (Jun 16–21):** signal→strategy→TWAK execution loop, autonomous via `serve --watch`, hard risk gates, backtest harness + frozen config, on-chain registration, public repo, demo video + writeup, DoraHacks submission.
- **Stretch (only if MVP lands early):** perps module (short/leverage convexity via a BSC perps DEX), hand-rolled BSC copy-trade signal from raw defi_events, richer ensemble tuning, agent "personality"/narration for demo appeal.

## 9. Timeline
- Jun 16–18: data plumbing (Monolit + CMC/x402 via TWAK), backtest harness, strategy engine v1.
- Jun 19–20: TWAK execution + autonomous loop + risk gates; dry-run on BSC with tiny size; register agent on-chain.
- Jun 21: freeze config, deploy to VPS, final repo + demo + DoraHacks submission. **Register before Jun 22.**
- Jun 22–28: live; monitor risk gates.

## 10. Success criteria
- Agent runs unattended for the full window, self-custody intact, ≥1 trade/day, never breaches the internal DD stop.
- All three stacks integrated non-cosmetically; x402 payments demonstrably working on-chain.
- Backtest shows positive risk-adjusted edge out-of-sample attributable to Monolit signals.
- Clean public repo + a demo that shows the end-to-end self-custody + x402 loop with BSC tx hashes.

## 11. Open questions / to confirm at build time
1. Exact x402 402-challenge schema from `pro-api.coinmarketcap.com` (payTo, asset addr, validity); whether the MCP host itself accepts x402 or needs a CMC key.
2. Whether multiple submissions per participant are allowed (on-chain is per-wallet; DoraHacks binds one address — assume one).
3. Monolit runtime access method for the agent (MCP client vs REST) + API keys.
4. Agent name / personality (affects demo; creative, decide later).
5. Confirm a BSC perps venue + TWAK/SDK path before committing to the perps stretch.
