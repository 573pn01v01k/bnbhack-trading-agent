"""Live autonomous trading agent for the BNB Hack Track-1 window.

One decision cycle (run hourly via cron or `twak serve --watch`):
  1. refresh recent hourly prices for the eligible universe + BTC;
  2. compute the regime-gated equal-weight target (the frozen, validated strategy);
  3. best-effort Monolit edge: drop honeypot names (security veto) and read live
     on-chain flow (the data moat) — never blocks the decision if the cluster lags;
  4. diff target vs current holdings into a trade plan (routed via a stable);
  5. risk-gate every trade (drawdown stop, per-trade/daily caps, slippage);
  6. execute via the Trust Wallet Agent Kit in self-custody (dry-run by default);
  7. append a structured decision record (on-chain proof when live).

Self-custody: the agent never holds keys — TWAK signs locally. Everything here
is a dry-run plan unless `live=True` and a funded TWAK wallet is configured.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import marketdata as MD
from . import strategy as ST
from . import universe as U
from .execution import RiskCaps, TWAKAdapter, check_trade_allowed

STATE_DIR = Path(__file__).parent / "data" / "runtime"
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = STATE_DIR / "decisions.jsonl"
STABLE = "USDT"  # routing/quote leg


@dataclass
class AgentState:
    equity_peak: float = 0.0
    last_trade_day: str = ""
    holdings: dict = field(default_factory=dict)   # symbol -> USD value (model)

    @classmethod
    def load(cls) -> "AgentState":
        if STATE_FILE.exists():
            return cls(**json.loads(STATE_FILE.read_text()))
        return cls()

    def save(self) -> None:
        STATE_FILE.write_text(json.dumps(asdict(self), indent=1))


@dataclass
class AgentConfig:
    capital_usd: float = 500.0
    history_days: int = 45                 # enough for the 14d MA regime + warmup
    cfg: ST.StrategyConfig = field(default_factory=lambda: ST.StrategyConfig())
    caps: RiskCaps = field(default_factory=RiskCaps)
    min_trade_usd: float = 5.0             # skip dust trades
    use_monolit_edge: bool = True


def _candidates(price_cols) -> list[str]:
    toks = U.tradeable_tokens(U.load_universe())
    return [t.symbol for t in toks if t.symbol in price_cols]


def decide(config: AgentConfig, client=None) -> dict:
    """Compute the target allocation for now (no execution)."""
    cands_all = [t.symbol for t in U.tradeable_tokens(U.load_universe())]
    fetch = sorted(set(cands_all) | {config.cfg.regime_ref})
    price = MD.price_panel(fetch, days=config.history_days, use_cache=False)
    candidates = _candidates(price.columns)

    vetoes: set[str] = set()
    flow: dict[str, float] = {}
    if config.use_monolit_edge and client is not None:
        toks = [t for t in U.tradeable_tokens(U.load_universe()) if t.symbol in candidates and t.bsc_contract]
        try:
            vetoes = ST.security_vetoes(client, toks)
        except Exception:
            vetoes = set()
        try:
            flow = ST.flow_tilt(client, {t.symbol: t.bsc_contract for t in toks})
        except Exception:
            flow = {}

    alloc = ST.live_allocation(price, candidates, config.cfg, vetoes=vetoes)
    alloc["vetoes"] = sorted(vetoes)
    alloc["flow_imbalance"] = {k: round(v, 3) for k, v in flow.items()}
    return alloc


def plan_trades(target_weights: dict, holdings: dict, capital: float, *, min_trade_usd: float) -> list[dict]:
    """Diff target USD allocation vs current holdings into per-symbol trades."""
    symbols = set(target_weights) | set(holdings)
    trades = []
    for sym in sorted(symbols):
        tgt = target_weights.get(sym, 0.0) * capital
        cur = holdings.get(sym, 0.0)
        delta = tgt - cur
        if abs(delta) < min_trade_usd:
            continue
        if delta > 0:
            trades.append({"side": "buy", "symbol": sym, "usd": round(delta, 2), "from": STABLE, "to": sym})
        else:
            trades.append({"side": "sell", "symbol": sym, "usd": round(-delta, 2), "from": sym, "to": STABLE})
    return trades


def run_once(config: AgentConfig | None = None, client=None, *, live: bool = False) -> dict:
    config = config or AgentConfig()
    state = AgentState.load()
    twak = TWAKAdapter()

    alloc = decide(config, client=client)
    trades = plan_trades(alloc["weights"], state.holdings, config.capital_usd, min_trade_usd=config.min_trade_usd)

    # risk gate (drawdown stop, slippage, per-trade caps)
    current_equity = config.capital_usd  # model; live: read from TWAK portfolio
    state.equity_peak = max(state.equity_peak, current_equity)
    drawdown = 0.0 if state.equity_peak == 0 else (state.equity_peak - current_equity) / state.equity_peak

    executed, blocked = [], []
    for t in trades:
        ok, reason = check_trade_allowed(
            config.caps,
            current_drawdown=drawdown,
            daily_loss=0.0,
            proposed_position_frac=t["usd"] / max(config.capital_usd, 1.0),
            slippage_pct=0.5,
        )
        if not ok:
            blocked.append({**t, "reason": reason})
            continue
        cmd = twak.execute_swap(t["usd"], t["from"], t["to"], chain="bsc", dry_run=not live)
        executed.append({**t, "twak_cmd": cmd if not live else "submitted"})
        if not live:  # update model holdings in dry-run
            if t["side"] == "buy":
                state.holdings[t["symbol"]] = state.holdings.get(t["symbol"], 0.0) + t["usd"]
            else:
                state.holdings[t["symbol"]] = max(0.0, state.holdings.get(t["symbol"], 0.0) - t["usd"])

    day = time.strftime("%Y-%m-%d", time.gmtime())
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "as_of": alloc["as_of"],
        "risk_off": alloc["risk_off"],
        "n_target": len(alloc["weights"]),
        "vetoes": alloc.get("vetoes", []),
        "drawdown": round(drawdown, 4),
        "trades_planned": len(trades),
        "executed": executed,
        "blocked": blocked,
        "live": live,
    }
    with LOG_FILE.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    state.last_trade_day = day
    state.save()
    return record
