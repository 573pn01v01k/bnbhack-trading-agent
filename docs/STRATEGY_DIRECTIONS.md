# Strategy directions and chosen wedge

## Candidate directions

1. **Regime-adaptive BNB/BSC momentum skill** — blend CMC OHLCV, CMC technical indicators, Fear & Greed / macro regime, and optional Monolit wallet-flow anomaly data. Backtestable, Track 2 native, can become Track 1 execution via TWAK.
2. **Funding/sentiment divergence perps agent** — CMC derivatives funding/open-interest + sentiment. Strong Track 1 scoring fit, but live perps execution is harder without TWAK credentials.
3. **Top-wallet copy-trader with risk filters** — Monolit wallet flow + BNB venue + TWAK execution. Highest Monolit edge, but relies most on external data and live execution.
4. **Narrative rotation skill** — CMC trending narratives + BNB ecosystem basket + liquidity/risk filters. Great demo/story; backtesting needs robust token universe history.

## Pick

Start with **Direction 1** as a Track 2-first agent:

- It satisfies the required sponsor capability with CMC Data API/MCP.
- It produces the exact deliverable Track 2 asks for: a backtestable strategy spec.
- It can be upgraded to Track 1 by routing accepted signals into TWAK quote-only / execution mode.
- Optional Monolit MCP improves alpha but does not make the submission dependent on non-sponsor data.

## AutoResearch-inspired loop

`propose candidates → backtest on available data → critique failure mode → mutate parameters/risk policy → select/export best spec`.

Judging alignment: optimize for returns, drawdown, risk-adjusted performance, and rule adherence rather than raw PnL only.
