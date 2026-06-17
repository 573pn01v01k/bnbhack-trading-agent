"""Complete BSC PancakeSwap DEX-liquidity scan for every eligible tradeable token.

Per-token swap_events scan (14d), writing INCREMENTALLY so partial progress survives
a timeout. Output: src/bnbhack_agent/data/dex_liquidity_full.json. Use to validate /
expand the investable set (`universe.dex_liquid_candidates`) beyond the seed cache.
Run in the background: it is slow (~60 sequential on-chain queries)."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

cfg = json.load(open(os.path.expanduser("~/.claude.json")))
m = cfg["mcpServers"]["monolit"]
os.environ["MONOLIT_MCP_URL"] = m["url"]
os.environ["MONOLIT_API_KEY"] = m["headers"]["X-Api-Key"]

from bnbhack_agent.monolit import MonolitClient, _rows
from bnbhack_agent import universe as U

OUT = os.path.join(os.path.dirname(__file__), "..", "src", "bnbhack_agent", "data", "dex_liquidity_full.json")
USDT = "0x55d398326f99059ff775485246999027b3197955"
WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"

c = MonolitClient(timeout=45, max_retries=2)
toks = [t for t in U.tradeable_tokens(U.load_universe()) if t.bsc_contract]
out = {"_note": "full 14d BSC DEX scan via evm.swap_events", "_threshold_weekly_usd": U.DEX_MIN_WEEKLY_USD}
done = 0
for t in toks:
    a = t.bsc_contract.lower()
    sql = (
        f"SELECT count() n, "
        f"sumIf(toFloat64(quote_coin_amount)/pow(10,quote_coin_decimals), quote_coin IN ('{USDT}','{WBNB}')) "
        f"+ sumIf(toFloat64(base_coin_amount)/pow(10,base_coin_decimals), base_coin IN ('{USDT}','{WBNB}')) AS vol "
        f"FROM evm.swap_events WHERE chain='bsc' AND block_time>now()-INTERVAL 14 DAY "
        f"AND (base_coin='{a}' OR quote_coin='{a}')"
    )
    try:
        r = _rows(c.query_evm(sql))
    except Exception as e:
        out[t.symbol] = {"error": str(e)[:80]}
        continue
    if r:
        n = int(r[0].get("n", 0) or 0)
        # vol counts the stable/WBNB leg; WBNB legs are in BNB units (rough) — n is the robust proxy
        out[t.symbol] = {"swaps_14d": n, "stable_leg_14d": round(float(r[0].get("vol", 0) or 0))}
    done += 1
    json.dump(out, open(OUT, "w"), indent=1)  # incremental persist

ranked = sorted([(s, d) for s, d in out.items() if isinstance(d, dict) and "swaps_14d" in d],
                key=lambda kv: -kv[1]["swaps_14d"])
print(f"scanned {done}/{len(toks)} tokens")
for s, d in ranked[:25]:
    print(f"  {s:10} swaps_14d={d['swaps_14d']:>7} stable_leg=${d['stable_leg_14d']:>14,}")
print("LIQUID (>=500 swaps/14d):", [s for s, d in ranked if d["swaps_14d"] >= 500])
print("wrote", OUT)
