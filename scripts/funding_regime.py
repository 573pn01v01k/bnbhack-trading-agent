"""New signal: BTC perp funding-rate regime (Monolit/Bybit, backtestable).
Hypothesis: when funding is extremely high, longs are crowded -> elevated reversal/
squeeze risk -> de-risk even if price still says risk-on. Test whether adding this
overlay to the ensemble's regime gate improves OOS + holdout (honestly; reject if not).
"""
from __future__ import annotations

import json, os, sys
import numpy as np, pandas as pd

sys.path.insert(0, "scripts"); import research as R  # noqa: E402
from bnbhack_agent import strategy as ST, portfolio as PF, marketdata as MD  # noqa: E402
from bnbhack_agent.monolit import MonolitClient, _rows  # noqa: E402

BTC_PERP = 1844


def get_btc_funding(days=130):
    cache = MD.CACHE / "btc_funding.parquet"
    if cache.exists():
        return pd.read_parquet(cache)["funding"]
    cfg = json.load(open(os.path.expanduser("~/.claude.json"))); m = cfg["mcpServers"]["monolit"]
    os.environ.setdefault("MONOLIT_MCP_URL", m["url"]); os.environ.setdefault("MONOLIT_API_KEY", m["headers"]["X-Api-Key"])
    c = MonolitClient(timeout=40, max_retries=3)
    # paginate with a small inline LIMIT (large LIMITs return CSV artifacts we can't parse)
    out, cursor = {}, None
    for _ in range(10):
        where = f"ticker_id={BTC_PERP}" + (f" AND funding_rate_timestamp < '{cursor}'" if cursor else "")
        rows = _rows(c.call_tool("query_cex_trading_data", {"query":
            f"SELECT funding_rate_timestamp AS t, funding_rate AS f FROM cex.bybit_funding_rate "
            f"WHERE {where} ORDER BY funding_rate_timestamp DESC LIMIT 50"}))
        if not rows:
            break
        for r in rows:
            out[pd.to_datetime(r["t"], utc=True)] = float(r["f"])
        cursor = min(r["t"] for r in rows)
        if len(rows) < 50:
            break
    if not out:
        raise RuntimeError("no funding rows returned")
    s = pd.Series(out).sort_index()
    s.to_frame("funding").to_parquet(cache)
    return s


def main():
    px = pd.read_parquet(MD.CACHE / "price_120d.parquet"); cand = R._candidates_like(px) if hasattr(R, "_candidates_like") else None
    cov = px.notna().mean(); trad = [t.symbol for t in R.U.tradeable_tokens(R.U.load_universe())]
    cand = [s for s in trad if s in px.columns and cov[s] > 0.85 and s != "BTC"]
    try:
        liq = R.U.liquidity_ranking(); cand = sorted(cand, key=lambda s: liq.get(s, 0.0), reverse=True)
    except Exception:
        pass

    fund = get_btc_funding().reindex(px.index, method="ffill")
    z = (fund - fund.rolling(24 * 30, min_periods=24 * 5).mean()) / fund.rolling(24 * 30, min_periods=24 * 5).std()
    print(f"BTC funding: {fund.notna().sum()} hourly points, z-range [{z.min():.1f}, {z.max():.1f}], "
          f"frac time z>1.5: {(z > 1.5).mean():.0%}, z>2: {(z > 2).mean():.0%}", flush=True)

    W = ST.ensemble_weights(px, cand)
    sub = px[W.columns]
    base = PF.strategy_returns(sub, W, cost_bps=ST.FROZEN.cost_bps)

    def overlay(thr):
        derisk = (z > thr).reindex(W.index).fillna(False)
        Wd = W.copy(); Wd.loc[derisk] = 0.0
        return PF.strategy_returns(sub, Wd, cost_bps=ST.FROZEN.cost_bps)

    def stats(r, lo, hi):
        seg = r.iloc[lo:hi]; eq = (1 + seg).cumprod(); peak = eq.cummax()
        return float(eq.iloc[-1] - 1), float(((peak - eq) / peak).max())

    n = len(px); hb = 21 * 24
    print("\n  variant            full_ret  full_dd | holdout_ret  holdout_dd", flush=True)
    fr, fd = stats(base, 0, n); hr, hd = stats(base, n - hb, n)
    print(f"  base (price gate)   {fr:+.1%}   {fd:.1%}  | {hr:+.1%}      {hd:.1%}", flush=True)
    for thr in (1.5, 2.0, 2.5):
        r = overlay(thr); fr, fd = stats(r, 0, n); hr, hd = stats(r, n - hb, n)
        print(f"  + funding z>{thr}      {fr:+.1%}   {fd:.1%}  | {hr:+.1%}      {hd:.1%}", flush=True)
    print("\nKeep only if it improves return AND/OR cuts drawdown without overfitting.", flush=True)


if __name__ == "__main__":
    main()
