"""Fetch + cache the on-chain flow panel (Monolit swap_events, BSC) for the
tradeable universe. Slow (one big query per token), so it logs progress and
saves incrementally to survive the flaky deriv cluster.

Run: PYTHONPATH=src python3 scripts/fetch_flow.py [days]
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bnbhack_agent import marketdata as MD  # noqa: E402
from bnbhack_agent import universe as U  # noqa: E402
from bnbhack_agent.monolit import MonolitClient  # noqa: E402

LOG = ROOT / "scripts" / "fetch_flow.log"


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with LOG.open("a") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    cfg = json.load(open(os.path.expanduser("~/.claude.json")))
    m = cfg["mcpServers"]["monolit"]
    os.environ.setdefault("MONOLIT_MCP_URL", m["url"])
    os.environ.setdefault("MONOLIT_API_KEY", m["headers"]["X-Api-Key"])

    client = MonolitClient(timeout=90, max_retries=4)
    tokens = [t for t in U.tradeable_tokens(U.load_universe()) if t.bsc_contract]
    log(f"flow fetch start: {len(tokens)} tokens x {days}d")

    imbalance: dict[str, pd.Series] = {}
    net: dict[str, pd.Series] = {}
    hours = days * 24
    for i, t in enumerate(tokens, 1):
        try:
            df = MD.fetch_token_flow(client, t, hours=hours)
        except Exception as e:  # noqa: BLE001
            log(f"  {i}/{len(tokens)} {t.symbol}: ERROR {type(e).__name__} {str(e)[:80]}")
            continue
        if df.empty or "net_vol" not in df.columns:
            log(f"  {i}/{len(tokens)} {t.symbol}: no data")
            continue
        total = (df["buy_vol"].astype(float) + df["sell_vol"].astype(float)).replace(0, pd.NA)
        imbalance[t.symbol] = (df["net_vol"].astype(float) / total).astype("float64")
        net[t.symbol] = df["net_vol"].astype("float64")
        log(f"  {i}/{len(tokens)} {t.symbol}: {len(df)} hourly rows")
        if i % 10 == 0:
            _save(imbalance, net, days)
            log(f"  ... checkpoint saved at {i}")
    _save(imbalance, net, days)
    log(f"flow fetch DONE: {len(imbalance)} tokens with flow")


def _save(imbalance: dict, net: dict, days: int) -> None:
    if imbalance:
        imb = pd.DataFrame(imbalance).sort_index()
        full = pd.date_range(imb.index.min(), imb.index.max(), freq="1h", tz="UTC")
        imb.reindex(full).to_parquet(MD.CACHE / f"flow_imbalance_{days}d.parquet")
    if net:
        pd.DataFrame(net).sort_index().to_parquet(MD.CACHE / f"flow_net_{days}d.parquet")


if __name__ == "__main__":
    main()
