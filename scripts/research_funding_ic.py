"""HYPOTHESIS: funding LEVEL and funding CHANGE on the eligible Binance universe's
Bybit perps carry information about short-term forward returns (8/24/72h), and
rising funding precedes continuation ("catch the upward move"). Test pooled
cross-sectional IC + tercile spreads, then walk-forward a point-in-time funding
tilt against the incumbent regime-gated ensemble. Honest verdict after costs.

Data: Bybit linear USDT perps (Monolit) funding_rate, aligned to the cached
Binance hourly price panel (price_120d.parquet). Point-in-time only.
"""
from __future__ import annotations

import json, os, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bnbhack_agent import marketdata as MD, portfolio as PF, universe as U  # noqa: E402
from bnbhack_agent.monolit import MonolitClient, _rows  # noqa: E402

LOG = ROOT / "scripts" / "test_funding_ic.log"
FUND_CACHE = MD.CACHE / "univ_funding_120d.parquet"
HOLDOUT_H = 21 * 24


def log(m):
    with LOG.open("a") as fh:
        fh.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")
    print(m, flush=True)


def _env():
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
    cfg = json.load(open(os.path.expanduser("~/.claude.json"))); m = cfg["mcpServers"]["monolit"]
    os.environ.setdefault("MONOLIT_MCP_URL", m["url"])
    os.environ.setdefault("MONOLIT_API_KEY", m["headers"]["X-Api-Key"])


def candidates(px):
    cov = px.notna().mean()
    trad = [t.symbol for t in U.tradeable_tokens(U.load_universe())]
    cand = [s for s in trad if s in px.columns and cov[s] > 0.85 and s != "BTC"]
    try:
        liq = U.liquidity_ranking(); cand = sorted(cand, key=lambda s: liq.get(s, 0.0), reverse=True)
    except Exception:
        pass
    return cand


import signal


class _Timeout(Exception):
    pass


def _with_timeout(secs, fn, *a, **k):
    def _h(*_):
        raise _Timeout()
    old = signal.signal(signal.SIGALRM, _h)
    signal.alarm(secs)
    try:
        return fn(*a, **k)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def resolve_id(client, coin):
    rows = _rows(client.call_tool("get_cex_ticker_info", {"query":
        f"SELECT max(id) AS id FROM cex.bybit_ticker_info FINAL WHERE category='linear' "
        f"AND quote_coin='USDT' AND status='Trading' AND base_coin_parsed='{coin}' LIMIT 2"}))
    if rows and rows[0].get("id") is not None:
        return int(rows[0]["id"])
    return None


def fetch_funding(client, coin, tid):
    """Funding history by ticker_id (no JOIN -> fast pages). Paginate small LIMIT to
    stay inline (no CSV artifact). ClickHouse DateTime needs 'YYYY-MM-DD HH:MM:SS'."""
    if tid is None:
        return pd.Series(dtype=float)
    out, cursor = {}, None
    for _ in range(8):  # 8*50 = up to 400 funding points (>120d at 8h)
        cur = f" AND funding_rate_timestamp < '{cursor}'" if cursor else ""
        rows = _rows(client.call_tool("query_cex_trading_data", {"query":
            f"SELECT funding_rate_timestamp AS t, funding_rate AS f FROM cex.bybit_funding_rate "
            f"WHERE ticker_id={tid}{cur} ORDER BY funding_rate_timestamp DESC LIMIT 50"}))
        if not rows:
            break
        for r in rows:
            out[pd.to_datetime(r["t"], utc=True)] = float(r["f"])
        oldest = min(pd.to_datetime(r["t"], utc=True) for r in rows)
        cursor = oldest.strftime("%Y-%m-%d %H:%M:%S")
        if len(rows) < 50 or oldest <= pd.Timestamp("2026-02-15", tz="UTC"):
            break
    return pd.Series(out).sort_index() if out else pd.Series(dtype=float)


def build_funding_panel(px):
    if FUND_CACHE.exists():
        return pd.read_parquet(FUND_CACHE)
    _env()
    client = MonolitClient(timeout=45, max_retries=2)
    cand = candidates(px)[:14]  # top-14 liquid; strategy only allocates to top-8 anyway
    log(f"fetching funding for top-{len(cand)} liquid candidates (JOIN resolve)")
    cols = {}
    for c in cand:
        try:
            tid = _with_timeout(60, resolve_id, client, c)
            s = _with_timeout(260, fetch_funding, client, c, tid)  # skip a coin if it hangs
        except Exception as e:
            s = pd.Series(dtype=float); log(f"  {c}: ERR {type(e).__name__}")
        if len(s):
            cols[c] = s
        log(f"  {c}: {len(s)} funding pts")
    if not cols:
        raise RuntimeError("no funding fetched for any candidate")
    fund = pd.DataFrame(cols).sort_index()
    fund.index = pd.to_datetime(fund.index, utc=True)
    # forward-fill onto the hourly price index (funding known at its stamp, held until next)
    fund = fund.reindex(px.index, method="ffill")
    fund.to_parquet(FUND_CACHE)
    return fund


def ic_block(fund, fwd, label):
    """Pooled cross-sectional Spearman IC averaged over bars (each bar: rank tokens by
    signal vs rank by forward return). Sub-sample every 6h to keep overlap honest-ish."""
    ics = []
    idx = fund.index[::6]
    for ts in idx:
        d = pd.concat([fund.loc[ts], fwd.loc[ts]], axis=1).dropna()
        if len(d) >= 6:
            ics.append(d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman"))
    ic = float(np.nanmean(ics)) if ics else float("nan")
    se = float(np.nanstd(ics) / np.sqrt(len(ics))) if ics else float("nan")
    log(f"  IC({label}): {ic:+.4f}  (t~{ic/se:+.1f}, n_bars={len(ics)})")
    return ic


def tercile(sig, fwd, names, label):
    obs = pd.DataFrame({"s": sig.stack(), "r": fwd.stack()}).dropna()
    if len(obs) < 200:
        log(f"  tercile {label}: too few obs ({len(obs)})"); return
    try:
        obs["b"] = pd.qcut(obs["s"], 3, labels=names, duplicates="drop")
    except Exception:
        log(f"  tercile {label}: qcut failed"); return
    g = obs.groupby("b", observed=True)["r"].mean()
    parts = "  ".join(f"{k}={v:+.3%}" for k, v in g.items())
    spread = (g.iloc[-1] - g.iloc[0]) if len(g) >= 2 else float("nan")
    log(f"  tercile {label} (fwd24h, n={len(obs)}): {parts} | hi-lo={spread:+.3%}")


# ---- strategy pieces (mirror research.py conventions) -------------------
def regime_off(px, ma, ref="BTC"):
    r = px[ref]; return (r < r.rolling(ma).mean()).fillna(False)


def ew_returns(px, cols, ma, cost=10.0):
    sub = px[cols]
    w = sub.notna().astype("float64")
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w.loc[regime_off(px, ma)] = 0.0
    return PF.strategy_returns(sub, w, cost_bps=cost)


def ensemble_returns(px, cand, ns=(3, 5, 8), mas=(240, 336, 480), cost=10.0):
    parts = [ew_returns(px, cand[:n], ma, cost) for n in ns for ma in mas]
    return sum(parts) / len(parts)


def funding_tilt_returns(px, cand, fund_z, ma, alpha, ns=(3, 5, 8), mas=(240, 336, 480), cost=10.0):
    """Incumbent ensemble structure, but each sleeve's EW basket is tilted by a
    funding signal: weight_i *= clip(1 + alpha * z_i, 0, 3). z is cross-sectional,
    point-in-time. Negative alpha = underweight high-funding (crowded longs);
    positive alpha = overweight high funding (chase momentum)."""
    parts = []
    for n in ns:
        cols = cand[:n]
        sub = px[cols]
        z = fund_z[cols].reindex(px.index)
        tilt = (1 + alpha * z.fillna(0.0)).clip(lower=0.0, upper=3.0)
        base = sub.notna().astype("float64") * tilt
        base = base.div(base.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        for m in mas:
            bb = base.copy(); bb.loc[regime_off(px, m)] = 0.0
            parts.append(PF.strategy_returns(sub, bb, cost_bps=cost))
    return sum(parts) / len(parts)


def stats(r, lo, hi):
    seg = r.iloc[lo:hi]; eq = (1 + seg).cumprod(); peak = eq.cummax()
    mdd = float(((peak - eq) / peak).max()) if len(seg) else 0.0
    sig = seg.std(); sh = float(seg.mean() / sig * np.sqrt(24 * 365)) if sig > 0 else 0.0
    return float(eq.iloc[-1] - 1) if len(seg) else 0.0, mdd, sh


def main():
    px = pd.read_parquet(MD.CACHE / "price_120d.parquet")
    cand = candidates(px)
    fund = build_funding_panel(px)
    fund = fund.reindex(columns=[c for c in cand if c in fund.columns])
    log(f"funding panel: {fund.shape}, coverage {fund.notna().mean().mean():.0%}, "
        f"{fund.index.min()}..{fund.index.max()}")

    # signals known at t
    dfund = fund.diff(24)  # funding change over ~24h (3 funding intervals)
    # cross-sectional z of funding level at each bar (point in time)
    z = fund.sub(fund.mean(axis=1), axis=0).div(fund.std(axis=1).replace(0, np.nan), axis=0)

    log("=== INFORMATION COEFFICIENT (Spearman, pooled cross-section) ===")
    rprice = px[fund.columns]
    for hours in (8, 24, 72):
        fwd = rprice.shift(-hours) / rprice - 1.0
        ic_block(fund, fwd, f"funding_level -> {hours}h")
        ic_block(dfund, fwd, f"funding_change24 -> {hours}h")

    log("=== TERCILE forward-24h returns ===")
    fwd24 = rprice.shift(-24) / rprice - 1.0
    tercile(fund, fwd24, ["low_fund", "mid", "high_fund"], "funding_level")
    tercile(dfund, fwd24, ["falling", "flat", "rising"], "funding_change24")

    log("=== WALK-FORWARD: funding tilt vs incumbent ensemble ===")
    base = ensemble_returns(px, cand)
    n = len(px); search = n - HOLDOUT_H
    TRAIN, TEST = 24 * 21, 24 * 7

    def wf(ret_by_param):
        st, oos = 0, []
        keys = list(ret_by_param)
        while st + TRAIN + TEST <= search:
            tr = slice(st, st + TRAIN); te = slice(st + TRAIN, st + TRAIN + TEST)
            best, bk = None, (-9, -9)
            for k in keys:
                m = PF.metrics_from_returns(ret_by_param[k].iloc[tr])
                key = (0 if m.max_drawdown > 0.30 else 1, m.sharpe)
                if key > bk: bk, best = key, k
            oos.append(ret_by_param[best].iloc[te]); st += TEST
        return PF.metrics_from_returns(pd.concat(oos)) if oos else None

    # incumbent as a single "param" walk-forward (it self-selects nothing; constant)
    base_oos = wf({"base": base})
    log(f"  INCUMBENT ensemble : OOS ret={base_oos.total_return:+.1%} sharpe={base_oos.sharpe:.2f} dd={base_oos.max_drawdown:.1%}")

    grid = {}
    for a in (-2.0, -1.0, -0.5, 0.5, 1.0, 2.0):
        grid[f"tilt_a{a}"] = funding_tilt_returns(px, cand, z, 336, a)
    tilt_oos = wf(grid)
    log(f"  FUNDING TILT (wf a) : OOS ret={tilt_oos.total_return:+.1%} sharpe={tilt_oos.sharpe:.2f} dd={tilt_oos.max_drawdown:.1%}")

    # locked holdout: representative configs on last 21d (full-panel returns, warm MA)
    log("=== LOCKED 21d HOLDOUT (full-panel, warm MA) ===")
    br, bd, bs = stats(base, n - HOLDOUT_H, n)
    log(f"  incumbent ensemble : ret={br:+.1%} dd={bd:.1%} sharpe={bs:.2f}")
    for a in (-1.0, -0.5, 0.5, 1.0):
        r = funding_tilt_returns(px, cand, z, 336, a)
        hr, hd, hs = stats(r, n - HOLDOUT_H, n)
        log(f"  tilt a={a:+.1f}       : ret={hr:+.1%} dd={hd:.1%} sharpe={hs:.2f}")
    log("DONE")


if __name__ == "__main__":
    main()
