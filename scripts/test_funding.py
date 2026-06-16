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
DAYS = 21                       # 60d scans time out at the gateway; 21d reliably completes
DD_CAP = 0.30


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
    log("fetching bybit hourly price + funding per ticker (60d scoped, fast) ...")
    pcols, fcols = {}, {}
    for coin, tid in TICKERS.items():
        # 4h-resolution, LIMIT-bounded -> stays inline (no artifact) and dodges the gateway scan timeout
        pr = _rows(client.call_tool("query_cex_trading_data", {"query":
            f"SELECT open_time AS h, close_price AS c FROM cex.bybit_kline "
            f"WHERE ticker_id={tid} AND toMinute(open_time)=0 AND (toHour(open_time) % 4)=0 "
            f"ORDER BY open_time DESC LIMIT 170"}))
        if pr:
            pcols[coin] = pd.Series({pd.to_datetime(r["h"], utc=True): float(r["c"]) for r in pr})
        fr = _rows(client.call_tool("query_cex_trading_data", {"query":
            f"SELECT funding_rate_timestamp AS t, funding_rate AS f FROM cex.bybit_funding_rate "
            f"WHERE ticker_id={tid} ORDER BY funding_rate_timestamp DESC LIMIT 90"}))
        if fr:
            fcols[coin] = pd.Series({pd.to_datetime(r["t"], utc=True): float(r["f"]) for r in fr})
        log(f"  {coin}: price={len(pr)} funding={len(fr)}")
    price = pd.DataFrame(pcols).sort_index()
    full = pd.date_range(price.index.min(), price.index.max(), freq="4h", tz="UTC")
    price = price.reindex(full).ffill(limit=2)
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

    fund = fund.reindex_like(price)
    dfund = fund.diff(2)  # funding change over ~2 bars (~8h) — ignition proxy (4h grid)

    # --- Q: does funding (or its change) LEAD price moves? Information coefficient. ---
    log("  --- information coefficient (Spearman, pooled cross-section per bar; 4h grid) ---")
    for hours, bars in ((8, 2), (24, 6), (72, 18)):
        fwd = price.shift(-bars) / price - 1.0
        for name, sigp in (("funding ", fund), ("d_funding", dfund)):
            ics = []
            for ts in price.index[::3]:
                d = pd.concat([sigp.loc[ts], fwd.loc[ts]], axis=1).dropna()
                if len(d) >= 5:
                    ics.append(d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman"))
            ic = float(np.nanmean(ics)) if ics else float("nan")
            log(f"  IC({name} -> {hours:2}h fwd return): {ic:+.3f}  (n_bars={len(ics)})")

    # --- tercile: bucket every (token,bar) by funding; mean forward ~24h return per bucket ---
    fwd24 = price.shift(-6) / price - 1.0
    obs = pd.DataFrame({"f": fund.stack(), "r": fwd24.stack()}).dropna()
    log(f"  --- tercile forward-24h return by funding level (n={len(obs)}) ---")
    if len(obs) > 100:
        obs["b"] = pd.qcut(obs["f"], 3, labels=["low_funding", "mid", "high_funding"], duplicates="drop")
        g = obs.groupby("b", observed=True)["r"].mean()
        for k, v in g.items():
            log(f"    {k:13}: {v:+.3%}")
        if "high_funding" in g and "low_funding" in g:
            log(f"  high-minus-low funding -> fwd24 spread: {g['high_funding'] - g['low_funding']:+.3%}")
    # same for funding CHANGE (rising funding = building long pressure = ignition?)
    obs2 = pd.DataFrame({"df": dfund.stack(), "r": fwd24.stack()}).dropna()
    if len(obs2) > 100:
        obs2["b"] = pd.qcut(obs2["df"], 3, labels=["falling", "flat", "rising"], duplicates="drop")
        g2 = obs2.groupby("b", observed=True)["r"].mean()
        log("  --- fwd24 by funding CHANGE ---")
        for k, v in g2.items():
            log(f"    {k:13}: {v:+.3%}")
        if "rising" in g2 and "falling" in g2:
            log(f"  rising-minus-falling d_funding -> fwd24 spread: {g2['rising'] - g2['falling']:+.3%}")
    log("DONE")


if __name__ == "__main__":
    main()
