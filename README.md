# BNB Hack — Autonomous Self-Custody Trading Agent (Track 1)

Submission for **BNB Hack: AI Trading Agent Edition** (BNB Chain × CoinMarketCap × Trust Wallet).
Target: **Track 1 — Autonomous Trading Agents** + the **Best Use of Trust Wallet Agent Kit** special.

A self-custodial autonomous agent that trades live on BSC over the Jun 22–28 window. Its market-read
brain runs on a crypto data layer most teams won't have — **Monolit** live on-chain BSC flow + CEX
derivatives, layered on **CoinMarketCap's Agent Hub** — it decides allocation under hard risk rules,
and signs/executes every trade itself through the **Trust Wallet Agent Kit** in unattended
self-custody mode. It pays for its data keyless, per request, via **x402**.

> Full design: [`docs/superpowers/specs/2026-06-16-bnbhack-trading-agent-design.md`](docs/superpowers/specs/2026-06-16-bnbhack-trading-agent-design.md)

## Result (walk-forward, out-of-sample — full report in `docs/BACKTEST_RESULTS_TRACK1.md`)

Validated on **120 days of real hourly data** across **64 eligible BEP-20 tokens**. Every number is stitched out-of-sample (the only hyperparameter, the regime MA, is chosen on each train window and applied to the next unseen window):

| Strategy (stitched OOS) | Return | Sharpe | Max DD |
|---|---:|---:|---:|
| **Regime-gated EW, top-10 liquid (LIVE)** | **+16.5%** | **1.72** | **16.4%** |
| Regime-gated EW, full 64 | +11.9% | 1.50 | 14.7% |
| Equal-weight basket (baseline) | +7.0% | 0.75 | 27.9% |
| BTC buy-and-hold | −2.4% | −0.02 | 28.0% |
| Cross-sectional momentum | **−63%** (REJECTED — overfit) | −4.1 | 67.8% |

Spot-only, no leverage. The strategy beats the basket on return, Sharpe, and drawdown, well inside the 30% DQ gate. Naive momentum/reversal/vol-concentration were tested under the same protocol and rejected — the engine exposes overfitting instead of hiding it.

**Concentration is the leaderboard lever:** a winner-take-all 7-day contest rewards the right tail, not Sharpe. Shrinking the basket leaves expected return flat-to-up but fattens the weekly right tail (max 7-day return: **+14% at N=64 → +28% at N=5**, P(week >15%): 0% → 2.4%) while the regime gate keeps worst-case drawdown under the gate. Reproduce: `python3 -m bnbhack_agent.cli track1-backtest`.

## How it works

- **Strategy** (`strategy.py`): hold a diversified equal-weight basket of the eligible tokens when BTC is risk-on (above its ~14-day MA); rotate fully to the stablecoin leg otherwise. Same function drives backtest and live (decision parity).
- **Data moat** (`monolit.py`): live Monolit MCP client — on-chain BSC swap flow (`evm.swap_events`), CEX derivatives, token security — used as a live veto/tilt competitors using CMC-only do not have.
- **Engine** (`marketdata.py`, `signals.py`, `portfolio.py`, `walkforward.py`): cached price/flow panels, no-lookahead simulator, walk-forward OOS evaluation vs baselines.
- **Execution** (`execution.py`): Trust Wallet Agent Kit in self-custody — `twak swap --chain bsc`, x402-paid data, `automate` cadence, `serve --watch` for unattended signing. Risk caps gate every trade (drawdown stop inside the 30% gate, per-trade/daily limits, slippage).
- **Registration** (`register.py`): the BSC `CompetitionRegistry` (optional `web3` extra).
- **Agent** (`agent.py`): hourly decision → risk-gated trade plan → self-custody execution → structured decision log.

`cmc_skill.py` (a Track‑2 Strategy Skill exporter) is carried over but is not part of this Track‑1 submission. Tests: **70 passing**.

## Usage

```bash
python3 -m pip install -e .                 # optionally: pip install 'web3>=6'  (on-chain registration)
python3 -m pytest -q                         # 70 passed
PYTHONPATH=src python3 -m bnbhack_agent.cli track1-backtest          # reproduce the OOS result
PYTHONPATH=src python3 -m bnbhack_agent.cli track1-run               # one decision cycle (dry-run)
MONOLIT_API_KEY=... PYTHONPATH=src python3 -m bnbhack_agent.cli track1-run --monolit  # with the live edge
PYTHONPATH=src python3 -m bnbhack_agent.cli track1-register          # registration window/status
```

## The contest, briefly

149 eligible BEP-20 tokens; portfolio valued in USD hour-by-hour; ranked by **% return** with simulated
costs; **30% max-drawdown = disqualification**; ≥1 trade/day. Registration on the BSC `CompetitionRegistry`
`0x212c61b9b72c95d95bf29cf032f5e5635629aed5` before the Jun 22 trading window. See `docs/HACKATHON_RULES.md`.

## Quickstart (baseline engine)

```bash
python3 -m pip install -e .
python3 -m pytest -q
PYTHONPATH=src python3 -m bnbhack_agent.cli battle --source binance --symbols BNB --count 1000 --out runs/battle_bnb --train-ratio 0.70
```

## Disclaimer

Research and live-trading software. Not financial advice. Trades on-chain with real funds and can lose money.
