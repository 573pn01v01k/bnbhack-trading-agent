"""DEX ignition / arb front-run hypothesis test.

Signal (point-in-time, no lookahead): for an eligible BSC token, count DEX swaps
per hour from evm.swap_events. Flag an 'ignition' bar t when the swap count z-score
vs the TRAILING 168h window (rows t-168..t-1, current bar EXCLUDED) >= threshold.
Ignition timestamps were extracted server-side in ClickHouse (see hypothesis doc).

Test: does an ignition at hour t predict positive forward price return t -> t+h on the
cached Binance hourly panel? Entry is at t+1 (signal is only known at close of t), so
there is no lookahead. Compare ignition forward returns vs the token's unconditional
(all-bar) forward returns, net of a one-way TWAK cost (gas+slippage).
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bnbhack_agent import marketdata as MD  # noqa

px = pd.read_parquet(MD.CACHE / "price_120d.parquet")
px.index = pd.to_datetime(px.index, utc=True)

# ignition timestamps (UTC hour) extracted from ClickHouse, point-in-time z-score
IGN = {
    ("CAKE", "z>=3"): "2026-02-19T13,2026-02-23T01,2026-02-23T21,2026-02-25T13,2026-02-28T06,2026-02-28T07,2026-03-02T15,2026-03-06T22,2026-03-14T07,2026-03-15T12,2026-03-15T13,2026-03-23T11,2026-03-26T01,2026-03-27T05,2026-03-28T05,2026-03-28T23,2026-03-29T04,2026-03-30T03,2026-04-03T20,2026-04-04T00,2026-04-07T03,2026-04-07T05,2026-04-07T22,2026-04-10T11,2026-04-14T15,2026-04-20T04,2026-04-22T03,2026-04-27T10,2026-04-28T10,2026-04-29T05,2026-04-30T15,2026-04-30T16,2026-04-30T19,2026-05-01T04,2026-05-01T08,2026-05-01T15,2026-05-04T03,2026-05-04T04,2026-05-06T13,2026-05-07T01,2026-05-07T08,2026-05-11T17,2026-05-12T14,2026-05-17T00,2026-05-29T14,2026-05-30T16,2026-05-30T17,2026-05-31T03,2026-06-01T05,2026-06-01T06,2026-06-01T11,2026-06-01T15,2026-06-01T22,2026-06-04T02,2026-06-05T06,2026-06-05T14,2026-06-05T16,2026-06-06T04",
    ("CAKE", "z2-3"): "2026-02-20T13,2026-02-21T02,2026-02-21T04,2026-02-23T17,2026-02-24T14,2026-02-26T16,2026-03-03T14,2026-03-06T12,2026-03-06T14,2026-03-09T15,2026-03-13T14,2026-03-13T15,2026-03-13T16,2026-03-13T20,2026-03-15T11,2026-03-25T12,2026-03-27T11,2026-03-28T21,2026-04-01T03,2026-04-02T16,2026-04-03T19,2026-04-04T10,2026-04-08T05,2026-04-11T15,2026-04-11T18,2026-04-13T17,2026-04-13T18,2026-04-14T13,2026-04-14T14,2026-04-15T03,2026-04-17T02,2026-04-17T14,2026-04-19T10,2026-04-20T05,2026-04-30T13,2026-05-01T16,2026-05-02T15,2026-05-04T00,2026-05-06T10,2026-05-09T18,2026-05-11T16,2026-05-11T20,2026-05-12T15,2026-05-12T16,2026-05-13T02,2026-05-13T03,2026-05-13T04,2026-05-13T05,2026-05-13T06,2026-05-13T07,2026-05-13T08,2026-05-13T09,2026-05-13T10,2026-05-13T11,2026-05-13T12,2026-05-13T13,2026-05-13T14,2026-05-13T15,2026-05-13T16,2026-05-17T01,2026-05-20T22,2026-05-22T02,2026-05-29T03,2026-05-30T18,2026-05-30T19,2026-05-31T01,2026-05-31T04,2026-05-31T05,2026-06-01T09,2026-06-01T10,2026-06-01T13,2026-06-01T14,2026-06-01T16,2026-06-02T09,2026-06-04T00,2026-06-04T01,2026-06-04T05,2026-06-05T15,2026-06-08T15,2026-06-09T00,2026-06-14T00",
    ("ASTER", "z>=3"): "2026-02-23T01,2026-02-23T02,2026-02-23T03,2026-02-23T04,2026-02-24T02,2026-02-24T13,2026-02-24T14,2026-02-26T17,2026-02-27T11,2026-02-27T13,2026-02-27T15,2026-02-27T17,2026-02-28T06,2026-02-28T07,2026-02-28T08,2026-02-28T09,2026-02-28T10,2026-02-28T12,2026-02-28T13,2026-03-11T11,2026-03-13T19,2026-03-16T03,2026-03-16T20,2026-03-16T21,2026-03-16T23,2026-03-17T00,2026-03-17T01,2026-03-17T02,2026-03-17T03,2026-03-17T13,2026-03-17T14,2026-03-17T15,2026-03-17T16,2026-03-18T13,2026-03-18T14,2026-03-26T13,2026-04-02T07,2026-04-06T13,2026-04-11T20,2026-04-12T12,2026-04-14T10,2026-04-14T11,2026-04-14T12,2026-04-17T13,2026-04-17T14,2026-04-17T15,2026-04-17T16,2026-04-18T07,2026-04-19T08,2026-04-24T13,2026-04-25T21,2026-04-25T22,2026-04-25T23,2026-04-26T00,2026-04-26T01,2026-04-26T02,2026-04-26T03,2026-04-26T04,2026-04-26T06,2026-04-26T07,2026-04-26T13,2026-04-26T14,2026-04-27T05,2026-05-02T16,2026-05-04T08,2026-05-04T10,2026-05-06T11,2026-05-07T03,2026-05-07T17,2026-05-09T01,2026-05-09T02,2026-05-09T04,2026-05-09T05,2026-05-09T06,2026-05-09T07,2026-05-09T09,2026-05-09T14,2026-05-09T21,2026-05-10T16,2026-05-10T17,2026-05-10T19,2026-05-10T20,2026-05-10T21,2026-05-21T10,2026-05-21T14,2026-05-21T16,2026-05-21T17,2026-05-24T10,2026-05-24T13,2026-05-30T19,2026-05-31T03,2026-05-31T06,2026-05-31T07,2026-05-31T08,2026-05-31T09,2026-05-31T11,2026-05-31T12,2026-05-31T13,2026-05-31T14,2026-06-02T18,2026-06-09T03,2026-06-10T16,2026-06-10T17",
}

HOLD_START = pd.Timestamp("2026-05-26 16:00", tz="UTC")  # last 21 days locked holdout
HORIZONS = [1, 4, 12, 24]
COST = 20e-4  # one-way TWAK ~20bps; round trip = 2x


def parse(ts_csv):
    return pd.to_datetime([t + ":00:00Z" for t in ts_csv.split(",")], utc=True)


def fwd_ret(series, t, h):
    """price return t -> t+h, entered at t+1 (no lookahead). Uses bar t+1..t+h move
    so the position is opened the bar AFTER the signal."""
    idx = series.index
    if t not in idx:
        return np.nan
    pos = idx.get_loc(t)
    if pos + 1 + h >= len(idx):
        return np.nan
    p0 = series.iloc[pos + 1]   # entry next bar
    p1 = series.iloc[pos + 1 + h]
    if not (p0 > 0 and p1 > 0):
        return np.nan
    return p1 / p0 - 1.0


def analyze(sym, label, ts, split=None):
    if sym not in px.columns:
        return None
    s = px[sym].dropna()
    rows = []
    for h in HORIZONS:
        ig = [fwd_ret(s, t, h) for t in ts if (split is None or
              (split == "train" and t < HOLD_START) or (split == "hold" and t >= HOLD_START))]
        ig = [x for x in ig if not np.isnan(x)]
        # unconditional baseline: every bar's h-forward return
        base = (s.shift(-h) / s - 1.0).dropna()
        if not ig:
            continue
        ig = np.array(ig)
        # round-trip cost charged once per ignition trade
        net = ig.mean() - 2 * COST
        rows.append({
            "sym": sym, "sig": label, "split": split or "all", "h": h, "n": len(ig),
            "mean_gross": round(ig.mean() * 100, 3),
            "median": round(float(np.median(ig)) * 100, 3),
            "winrate": round((ig > 0).mean() * 100, 1),
            "base_mean": round(base.mean() * 100, 3),
            "edge_vs_base": round((ig.mean() - base.mean()) * 100, 3),
            "mean_net_cost": round(net * 100, 3),
            "t_stat": round(ig.mean() / (ig.std(ddof=1) / np.sqrt(len(ig))), 2) if len(ig) > 1 and ig.std() > 0 else 0.0,
        })
    return pd.DataFrame(rows)


out = []
for (sym, label), csv in IGN.items():
    ts = parse(csv)
    for split in ["all", "train", "hold"]:
        df = analyze(sym, label, ts, None if split == "all" else split)
        if df is not None and len(df):
            out.append(df)

res = pd.concat(out, ignore_index=True)
pd.set_option("display.width", 200, "display.max_columns", 50, "display.max_rows", 200)
print(res.to_string(index=False))

print("\n=== SUMMARY: net-of-cost mean forward return by signal/horizon (full sample) ===")
full = res[res.split == "all"]
print(full[["sym", "sig", "h", "n", "mean_gross", "mean_net_cost", "edge_vs_base", "winrate", "t_stat"]].to_string(index=False))
