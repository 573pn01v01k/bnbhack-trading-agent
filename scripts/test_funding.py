"""Test Pavel's high-vol 'crimes' thesis honestly: is CEX FUNDING a LEADING signal
for moves on the degen universe (LAB, RAVE, MYX, ... — Bybit perps, no Binance)?

Data: Bybit (Monolit main cluster) — hourly close (5m kline aggregated) + 8h funding.
Tests: (1) information coefficient of funding[t] vs forward return; (2) funding-based
selection backtests under walk-forward OOS + locked 21d holdout.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bnbhack_agent import marketdata as MD, portfolio as PF  # noqa: E402
from bnbhack_agent.monolit import MonolitClient, _rows  # noqa: E402

LOG = ROOT / "scripts" / "test_funding.log"
TICKERS = {  # coin -> Bybit linear ticker_id
    "ASTER": 5723584, "BANANAS31": 1811, "BEAT": 12249730, "COAI": 6830249, "CYS": 22157519,
    "DEXE": 1891, "FF": 6576436, "GENIUS": 18023742, "HOME": 1978, "HUMA": 1982, "INJ": 1998,
    "KITE": 9847162, "LAB": 9169766, "MYX": 1734473, "NIGHT": 20805851, "RAVE": 23500439,
    "SAHARA": 2179, "SIREN": 2195, "STG": 2224, "TAG": 1059036, "XPL": 6205073, "ZEC": 2330,
}
DAYS = 120
HOLDOUT_H = 21 * 24
TRAIN_H, TEST_H, DD_CAP = 24 * 21, 24 * 7, 0.30


def log(m):
    with LOG.open("a") as fh:
        fh.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")
    print(m, flush=True)


def _client():
    cfg = json.load(open(os.path.expanduser("~/.claude.json"))); m = cfg["mcpServers"]["monolit"]
    os.environ.setdefault("MONOLIT_MCP_URL", m["url"]); os.environ.setdefault("MONOLIT_API_KEY", m["headers"]["X-Api-Key"])
    return MonolitClient(timeout=120, max_retries=4)


def fetch_panels(client):
    pc = MD.CACHE / f"bybit_price_{DAYS}d.parquet"
    fc = MD.CACHE / f"bybit_funding_{DAYS}d.parquet"
    if pc.exists() and fc.exists():
        return pd.read_parquet(pc), pd.read_parquet(fc)
    log("fetching bybit hourly price + funding per ticker ...")
    pcols, fcols = {}, {}
    for coin, tid in TICKERS.items():
        pr = _rows(client.call_tool("query_cex_trading_data", {"query":
            f"SELECT toStartOfHour(open_time) AS h, argMax(close_price, open_time) AS c "
            f"FROM cex.bybit_kline WHERE ticker_id={tid} AND open_time > now() - INTERVAL {DAYS} DAY GROUP BY h ORDER BY h"}))
        if pr:
            s = pd.Series({pd.to_datetime(r["h"], utc=True): float(r["c"]) for r in pr})
            pcols[coin] = s
        fr = _rows(client.call_tool("query_cex_trading_data", {"query":
            f"SELECT funding_rate_timestamp AS t, funding_rate AS f "
            f"FROM cex.bybit_funding_rate WHERE ticker_id={tid} AND funding_rate_timestamp > now() - INTERVAL {DAYS} DAY ORDER BY t"}))
        if fr:
            fcols[coin] = pd.Series({pd.to_datetime(r["t"], utc=True): float(r["f"]) for r in fr})
        log(f"  {coin}: price={len(pr)} funding={len(fr)}")
    price = pd.DataFrame(pcols).sort_index()
    full = pd.date_range(price.index.min(), price.index.max(), freq="1h", tz="UTC")
    price = price.reindex(full).ffill(limit=3)
    fund = pd.DataFrame(fcols).sort_index().reindex(price.index, method="ffill")
    price.to_parquet(pc); fund.to_parquet(fc)
    return price, fund


def wf_oos(ret_by_param):
    any_r = next(iter(ret_by_param.values())); n = len(any_r); start, oos = 0, []
    while start + TRAIN_H + TEST_H <= n:
        tr = slice(start, start + TRAIN_H); te = slice(start + TRAIN_H, start + TRAIN_H + TEST_H)
        best, bk = None, (-9, -9)
        for k, r in ret_by_param.items():
            m = PF.metrics_from_returns(r.iloc[tr]); key = (0 if m.max_drawdown > DD_CAP else 1, m.sharpe)
            if key > bk: bk, best = key, k
        oos.append(ret_by_param[best].iloc[te]); start += TEST_H
    return PF.metrics_from_returns(pd.concat(oos)) if oos else None


def main():
    client = _client()
    price, fund = fetch_panels(client)
    log(f"degen universe: {price.shape[1]} coins, {price.shape[0]} hourly bars, "
        f"{price.index.min()}..{price.index.max()}")

    # BTC regime from the Binance panel, aligned
    btc = pd.read_parquet(MD.CACHE / "price_120d.parquet")["BTC"].reindex(price.index, method="ffill")
    search = slice(0, len(price) - HOLDOUT_H)

    # --- (1) information coefficient: does funding[t] predict forward return? ---
    for H in (8, 24, 72):
        fwd = price.shift(-H) / price - 1.0
        f = fund.reindex_like(price)
        # pooled Spearman-ish via rank corr per bar then average
        ics = []
        for ts in price.index[::24]:  # sample daily to keep it cheap
            a, b = f.loc[ts], fwd.loc[ts]
            d = pd.concat([a, b], axis=1).dropna()
            if len(d) >= 5:
                ics.append(d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman"))
        ic = float(np.nanmean(ics)) if ics else float("nan")
        log(f"  IC(funding -> {H}h fwd return): {ic:+.3f}  (n_bars={len(ics)})")

    # --- (2) backtests: funding-based selection, regime-gated, walk-forward OOS + holdout ---
    def regime_off(ma): return (btc < btc.rolling(ma).mean()).fillna(False)

    def sel_returns(score, k, ma, cost=10.0):
        valid = price.notna() & score.notna()
        rank = score.where(valid).rank(axis=1, ascending=False, method="first")
        w = (rank <= k).astype("float64")
        w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        w.loc[regime_off(ma)] = 0.0
        return PF.strategy_returns(price, w, cost_bps=cost)

    fsm = fund.rolling(3, min_periods=1).mean()                 # smoothed funding (known at t)
    dfund = fund.diff(3)                                        # funding change (ignition proxy)
    families = {
        "degen_ew": {ma: sel_returns(price.notna().astype(float), 99, ma) for ma in (240, 336, 480)},
        "fund_high": {(k, ma): sel_returns(fsm, k, ma) for k in (3, 5, 8) for ma in (240, 336, 480)},
        "fund_low": {(k, ma): sel_returns(-fsm, k, ma) for k in (3, 5, 8) for ma in (240, 336, 480)},
        "fund_rising": {(k, ma): sel_returns(dfund, k, ma) for k in (3, 5, 8) for ma in (240, 336, 480)},
    }
    log("  --- funding-selection backtests (search-window walk-forward OOS) ---")
    res = {}
    for name, grid in families.items():
        s = {k: v.iloc[search] for k, v in grid.items()}
        o = wf_oos(s)
        res[name] = o
        if o:
            log(f"  {name:12} OOS: ret={o.total_return:+.1%} sharpe={o.sharpe:.2f} dd={o.max_drawdown:.1%}")
    # holdout check on the best
    best = max((k for k in res if res[k]), key=lambda k: res[k].total_return)
    grid = families[best]
    hold = {k: v.iloc[len(price) - HOLDOUT_H:] for k, v in grid.items()}
    ho = wf_oos(hold) if len(price) - HOLDOUT_H > TRAIN_H + TEST_H else None
    if ho:
        log(f"  HOLDOUT {best}: ret={ho.total_return:+.1%} sharpe={ho.sharpe:.2f} dd={ho.max_drawdown:.1%}")
    else:
        # holdout too short for a fold; report full-holdout single-param at sensible setting
        hp = list(families[best].values())[len(families[best]) // 2].iloc[len(price) - HOLDOUT_H:]
        m = PF.metrics_from_returns(hp)
        log(f"  HOLDOUT(full) {best}: ret={m.total_return:+.1%} sharpe={m.sharpe:.2f} dd={m.max_drawdown:.1%}")
    log("DONE")


if __name__ == "__main__":
    main()
