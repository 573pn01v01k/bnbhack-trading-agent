# Demo Video — shot-by-shot (Best Use of TWAK)

Target length **2:00–2:30**. The panel scores *self-custody depth*: the agent holds its own
keys, signs its own trades, pays for its own data on-chain. Every claim must be shown on screen
with a real terminal + a real BSCScan tx — no slides-only. Record at 1080p, terminal font ≥ 16pt.

Prereqs before recording: TWAK wallet created + funded (a little BNB for gas, a few $ of USDT on
BSC, a little USDC on Base for x402), `TWAK_ACCESS_ID` / `TWAK_HMAC_SECRET` / `TWAK_WALLET_PASSWORD`
set, repo public. Keep amounts tiny — this is a craft demo, not the live contest run.

---

## Shot 1 — Hook (0:00–0:15)

- **Screen:** the README hero + equity-curve chart.
- **VO:** "This is a fully autonomous trading agent for BNB Hack Track 1. It reads the market on a
  deep on-chain data layer, decides under hard risk rules, and — the part that matters — it holds
  its own keys and signs every trade itself through the Trust Wallet Agent Kit. No exchange, no
  human in the loop."

## Shot 2 — Self-custody wallet (0:15–0:35)

- **Screen:** `twak wallet show` (or `twak wallet address`) → the agent's own BSC address.
  Then BSCScan open on that address showing the funded balance.
- **VO:** "The agent owns this wallet. The private key is generated and held by TWAK, encrypted
  under a password — it never leaves the host, and I never pasted it anywhere."

## Shot 3 — On-chain registration (0:35–0:55)

- **Screen:** `twak compete status` → shows the deadline + not-registered, then
  `twak compete register` → prints the registration tx hash. Cut to BSCScan on that tx
  (`CompetitionRegistry 0x212c…aed5`) confirmed.
- **VO:** "It registers itself on the BNB Hack CompetitionRegistry with one command — here's the
  confirmed on-chain transaction."

## Shot 4 — Pay for data with x402 (0:55–1:20)

- **Screen:** `twak x402 ...` paying a data endpoint (or the agent's x402-paid data call), showing
  the micropayment tx on Base. Cut to the BaseScan tx.
- **VO:** "It pays for its market data keyless, per request, over x402 — an on-chain micropayment
  instead of an API-key contract. Here's the payment settling on Base."

## Shot 5 — The decision loop (1:20–1:50)

- **Screen:** `LIVE=0 ./scripts/deploy/run_cycle.sh` (or `track1-run`) running. Highlight the JSON:
  `risk_off`, `n_target`, `vetoes`, `trades_planned`. Point at `logs/decisions.jsonl`.
- **VO:** "Every four hours it reads the regime — Monolit on-chain flow and CMC's Agent Hub — sizes
  a two-sleeve book under a 20% trailing stop and a regime gate, and logs the decision. The same
  function runs the backtest and the live agent, so what we validated is what trades."

## Shot 6 — A live self-custody swap (1:50–2:15)

- **Screen:** the agent executes a small real swap on BSC, e.g.
  `twak swap --usd 5 USDT CAKE --chain bsc` (or a live `run_cycle.sh` cycle inside the window).
  Show TWAK signing, the returned tx hash, then BSCScan confirmed.
- **VO:** "And it executes — signing the swap itself and broadcasting to PancakeSwap. Here's the
  confirmed trade on-chain. Self-custody, end to end."

## Shot 7 — Honest close (2:15–2:30)

- **Screen:** the drawdown chart (worst −15.9% vs the −30% gate) + the red-team note.
- **VO:** "Validated on 120 days of real data, net of measured DEX slippage, with a locked holdout.
  We red-teamed our own +20% draft, found it would disqualify on real slippage, and shipped the
  honest version. Built to survive the drawdown gate and catch the right tail."

---

### Capture checklist
- [ ] Wallet address shot + BSCScan balance
- [ ] `twak compete register` tx hash → BSCScan confirmed
- [ ] x402 payment tx → BaseScan confirmed
- [ ] `run_cycle.sh` decision JSON + `logs/decisions.jsonl`
- [ ] Live `twak swap` tx hash → BSCScan confirmed
- [ ] Drawdown chart / red-team beat
- [ ] Keep every funded amount tiny; redact nothing sensitive (no keys, no passwords on screen)
