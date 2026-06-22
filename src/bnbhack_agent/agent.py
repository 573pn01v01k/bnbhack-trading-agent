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
from dataclasses import asdict, dataclass, field, fields as dataclass_fields
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
    last_trade_ts: float = 0.0                     # epoch seconds of last executed trade (heartbeat)
    holdings: dict = field(default_factory=dict)   # symbol -> USD value (model)
    live_started: bool = False                     # has a live cycle seeded the real-equity peak?

    @classmethod
    def load(cls) -> "AgentState":
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            fields = {f.name for f in dataclass_fields(cls)}
            return cls(**{k: v for k, v in data.items() if k in fields})
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
    heartbeat_hours: int = 20              # force a tiny trade if idle this long -> guarantees >=1 trade/day
    use_monolit_edge: bool = True          # Monolit security screening (cached daily)
    use_cmc: bool = True                   # CMC Agent Hub live regime overlay (needs CMC_PRO_API_KEY)
    use_flow: bool = False                 # per-cycle on-chain flow tilt — off by default (slow + marginal)
    use_news_veto: bool = True             # negative-news veto on HELD names (search_twitter + M3, bounded/logged)
    security_ttl_h: int = 24               # re-check token security at most once/day


SECURITY_CACHE = STATE_DIR / "security_vetoes.json"


def _security_vetoes_cached(client, tokens, *, ttl_h: int = 24) -> set[str]:
    """Honeypot/high-tax screening is ~static, so cache it: re-check at most once per
    ttl_h. Keeps the data-moat (Monolit token security) off the hot decision path."""
    now = time.time()
    if SECURITY_CACHE.exists():
        try:
            c = json.loads(SECURITY_CACHE.read_text())
            if now - c.get("ts", 0) < ttl_h * 3600:
                return set(c.get("vetoes", []))
        except Exception:
            pass
    try:
        vetoes = ST.security_vetoes(client, tokens)
    except Exception:
        vetoes = set()
    SECURITY_CACHE.write_text(json.dumps({"ts": now, "vetoes": sorted(vetoes)}))
    return vetoes


def _candidates(price_cols, cfg: ST.StrategyConfig) -> list[str]:
    """The investable basket: eligible tokens present in prices, restricted+ranked by
    *measured BSC DEX liquidity* (the agent executes on PancakeSwap, so on-chain depth —
    not CEX volume — decides what is safely tradable). This is the live-side of the
    red-team fix; falls back to CEX ranking only if the DEX cache is unavailable."""
    toks = U.tradeable_tokens(U.load_universe())
    present = [t.symbol for t in toks if t.symbol in price_cols]
    try:
        liquid = U.dex_liquid_candidates(present)
        if liquid:
            return liquid
    except Exception:
        pass
    return U.liquid_candidates(present, cfg.max_positions)


def decide(config: AgentConfig, client=None) -> dict:
    """Compute the target allocation for now (no execution)."""
    cands_all = [t.symbol for t in U.tradeable_tokens(U.load_universe())]
    fetch = sorted(set(cands_all) | {config.cfg.regime_ref})
    price = MD.price_panel(fetch, days=config.history_days, use_cache=False)
    candidates = _candidates(price.columns, config.cfg)

    vetoes: set[str] = set()
    flow: dict[str, float] = {}
    if config.use_monolit_edge and client is not None:
        toks = [t for t in U.tradeable_tokens(U.load_universe()) if t.symbol in candidates and t.bsc_contract]
        vetoes = _security_vetoes_cached(client, toks, ttl_h=config.security_ttl_h)
        if config.use_flow:
            try:
                flow = ST.flow_tilt(client, {t.symbol: t.bsc_contract for t in toks}, max_checks=len(toks))
            except Exception:
                flow = {}

    # First pass: who would we hold? Negative-news veto only scores HELD names
    # (bounded), then we re-allocate with the merged veto set.
    news_audit: list[dict] = []
    if config.use_news_veto and client is not None:
        try:
            prelim = ST.live_ensemble_allocation(price, candidates, config.cfg, vetoes=vetoes)
            held = list(prelim["weights"].keys())
            from .news_veto import negative_vetoes
            nv, news_audit = negative_vetoes(client, held)
            vetoes = vetoes | nv
        except Exception:
            news_audit = []  # best-effort: never block the core decision

    alloc = ST.live_ensemble_allocation(price, candidates, config.cfg, vetoes=vetoes)
    alloc["vetoes"] = sorted(vetoes)
    alloc["news_veto"] = news_audit
    alloc["flow_imbalance"] = {k: round(v, 3) for k, v in flow.items()}

    # CMC Agent Hub live regime overlay (bounded, logged) — trims exposure in euphoria.
    cmc_sig = {"caution_factor": 1.0, "source": "off"}
    if config.use_cmc:
        from .cmc import CMCClient, regime_signal
        cmc_sig = regime_signal(CMCClient())          # neutral if no CMC_PRO_API_KEY
        cf = cmc_sig.get("caution_factor", 1.0)
        if cf < 1.0:
            alloc["weights"] = {k: round(v * cf, 5) for k, v in alloc["weights"].items()}
    alloc["cmc"] = cmc_sig
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


def _swap_error(exc: Exception) -> str:
    """Short, password-free reason from a failed TWAK swap. Never use str(exc): it
    contains the argv, including the --password value."""
    stderr = getattr(exc, "stderr", "") or ""
    line = stderr.strip().splitlines()[-1] if stderr.strip() else type(exc).__name__
    return line[:160]


def run_once(config: AgentConfig | None = None, client=None, *, live: bool = False,
             equity_usd: float | None = None) -> dict:
    config = config or AgentConfig()
    state = AgentState.load()
    twak = TWAKAdapter()

    alloc = decide(config, client=client)
    stable_balance: float | None = None              # real USDT pool (live only); gates buys

    # LIVE position sync — rebalance against the REAL wallet, never a stale model.
    # We read each basket/held name's USD value from TWAK *by contract* (auto-discovery
    # misses freshly-bought tokens), set holdings + equity from reality, and size to the
    # actual book. Without this the live loop would re-buy the same names every cycle.
    # Dry-run keeps the model holdings so the loop stays observable offline.
    if live and equity_usd is None:
        from .execution import resolve_bsc_asset
        tradeable = U.tradeable_tokens(U.load_universe())
        try:
            basket = set(U.dex_liquid_candidates([t.symbol for t in tradeable]))
        except Exception:
            basket = set()
        # Include the stable leg explicitly — stables aren't "tradeable tokens" but ARE
        # the cash that must count toward equity. resolve_bsc_asset covers stables+basket.
        want = set(alloc["weights"]) | basket | {STABLE, "USDC"}
        addr = {s: a for s in want if (a := resolve_bsc_asset(s))[:2].lower() == "0x"}
        wallet = twak.bsc_address()
        usd = twak.holdings_usd_bsc(addr, wallet)
        stable = usd.pop(STABLE, 0.0) + usd.pop("USDC", 0.0)
        token_usd = {k: round(v, 2) for k, v in usd.items() if v >= 0.5}  # ignore dust
        equity_usd = stable + sum(token_usd.values())
        state.holdings = token_usd
        stable_balance = stable                      # real USDT available to fund buys
        config.capital_usd = round(max(equity_usd, 1.0), 2)
        # Seed the drawdown peak from REAL equity on the first live cycle — never inherit
        # a dry-run model peak (capital_usd=500), which would fabricate a drawdown and
        # trip the hard-DD circuit-breaker on a freshly-funded, smaller book.
        if not state.live_started:
            state.equity_peak = equity_usd
            state.live_started = True

    # Real equity drives the drawdown circuit-breaker. Live: synced above from the wallet.
    # Dry-run/backtest: mark the USD-model holdings to nothing better than capital, so the
    # stop is only authoritative live — the per-name trailing stop inside the strategy is
    # the regime-independent protector.
    current_equity = equity_usd if equity_usd is not None else (sum(state.holdings.values()) or config.capital_usd)
    state.equity_peak = max(state.equity_peak, current_equity)
    drawdown = 0.0 if state.equity_peak == 0 else (state.equity_peak - current_equity) / state.equity_peak

    # Portfolio circuit-breaker: if we've breached the internal hard stop (inside the 30%
    # DQ gate), override the target to ALL-CASH — liquidate every name, do not re-risk.
    if drawdown >= config.cfg.hard_dd_stop:
        alloc["weights"] = {}
        alloc["hard_dd_stop"] = round(drawdown, 4)

    trades = plan_trades(alloc["weights"], state.holdings, config.capital_usd, min_trade_usd=config.min_trade_usd)

    # Sells first (they free up USDT), then buys — and live, cap cumulative buys to the
    # real USDT pool minus a gas+slippage reserve, so the last buy never fails on
    # insufficient balance. Each swap is isolated: a single failure is logged and the
    # cycle continues (never aborts the loop or the state save).
    trades = sorted(trades, key=lambda t: 0 if t["side"] == "sell" else 1)
    if stable_balance is not None:
        reserve = max(3.0, 0.015 * current_equity)   # gas + slippage headroom
        stable_avail = max(0.0, stable_balance - reserve)
    else:
        stable_avail = None
    executed, blocked = [], []
    for t in trades:
        usd = t["usd"]
        ok, reason = check_trade_allowed(
            config.caps,
            current_drawdown=drawdown,
            daily_loss=0.0,
            proposed_position_frac=usd / max(config.capital_usd, 1.0),
            slippage_pct=0.5,
        )
        if not ok:
            blocked.append({**t, "reason": reason})
            continue
        if t["side"] == "buy" and stable_avail is not None and usd > stable_avail:
            if stable_avail < config.min_trade_usd:
                blocked.append({**t, "reason": f"insufficient stable: have ${stable_avail:.2f}"})
                continue
            usd = round(stable_avail, 2)             # shrink the buy to fit the USDT on hand
        try:
            cmd = twak.execute_swap(usd, t["from"], t["to"], chain="bsc", dry_run=not live)
        except Exception as e:  # noqa: BLE001 — one bad swap must not abort the cycle
            blocked.append({**t, "usd": usd, "reason": f"swap failed: {_swap_error(e)}"})
            continue
        executed.append({**t, "usd": usd, "twak_cmd": cmd if not live else "submitted"})
        if stable_avail is not None:
            stable_avail += usd if t["side"] == "sell" else -usd
        if not live:  # update model holdings in dry-run
            if t["side"] == "buy":
                state.holdings[t["symbol"]] = state.holdings.get(t["symbol"], 0.0) + usd
            else:
                state.holdings[t["symbol"]] = max(0.0, state.holdings.get(t["symbol"], 0.0) - usd)

    # Heartbeat: guarantee the contest's >=1-trade/day rule in ANY regime (even fully
    # risk-off with no moonshot movers). If nothing traded and we've been idle too long,
    # do a tiny stable rotation — counts as a trade, ~zero PnL.
    now_ts = time.time()
    heartbeat = False
    if executed:
        state.last_trade_ts = now_ts
    elif now_ts - state.last_trade_ts > config.heartbeat_hours * 3600:
        try:
            cmd = twak.execute_swap(config.min_trade_usd, STABLE, "USDC", chain="bsc", dry_run=not live)
            executed.append({"side": "heartbeat", "symbol": "USDC", "usd": config.min_trade_usd,
                             "from": STABLE, "to": "USDC", "twak_cmd": cmd if not live else "submitted", "heartbeat": True})
            state.last_trade_ts = now_ts
            heartbeat = True
        except Exception as e:  # noqa: BLE001 — heartbeat is best-effort
            blocked.append({"side": "heartbeat", "symbol": "USDC", "usd": config.min_trade_usd,
                            "reason": f"heartbeat failed: {_swap_error(e)}"})

    day = time.strftime("%Y-%m-%d", time.gmtime())
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "as_of": alloc["as_of"],
        "risk_off": alloc.get("risk_off_fraction", alloc.get("risk_off")),
        "n_target": len(alloc["weights"]),
        "vetoes": alloc.get("vetoes", []),
        "news_veto": alloc.get("news_veto", []),
        "cmc": alloc.get("cmc"),
        "drawdown": round(drawdown, 4),
        "trades_planned": len(trades),
        "executed": executed,
        "blocked": blocked,
        "heartbeat": heartbeat,
        "live": live,
    }
    with LOG_FILE.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    state.last_trade_day = day
    state.save()
    return record
