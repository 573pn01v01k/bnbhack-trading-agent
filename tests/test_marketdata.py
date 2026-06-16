"""Market-data assembly tests. Network is monkeypatched out — no Binance calls."""
import numpy as np
import pandas as pd

from bnbhack_agent import marketdata


def _synthetic_series(n=48, start="2026-01-01"):
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    return pd.Series(100.0 + np.arange(n), index=idx, dtype="float64")


def test_price_panel_assembles_columns(monkeypatch, tmp_path):
    # point the cache at a tmp dir so we never touch the real parquet cache
    monkeypatch.setattr(marketdata, "CACHE", tmp_path)

    def fake_fetch(symbol, *, days=120, **kwargs):
        # symbol arrives as "<SYM>USDT"; return the same synthetic series for each
        return _synthetic_series(48)

    monkeypatch.setattr(marketdata, "fetch_binance_hourly", fake_fetch)

    symbols = ["BTC", "ETH", "BNB"]
    df = marketdata.price_panel(symbols, days=10, use_cache=False)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == symbols
    # hourly UTC DatetimeIndex
    assert isinstance(df.index, pd.DatetimeIndex)
    assert str(df.index.tz) == "UTC"
    freq = df.index.to_series().diff().dropna().unique()
    assert len(freq) == 1 and freq[0] == pd.Timedelta(hours=1)


def test_price_panel_passes_pair_with_usdt(monkeypatch, tmp_path):
    monkeypatch.setattr(marketdata, "CACHE", tmp_path)
    seen = []

    def fake_fetch(symbol, *, days=120, **kwargs):
        seen.append(symbol)
        return _synthetic_series(24)

    monkeypatch.setattr(marketdata, "fetch_binance_hourly", fake_fetch)
    marketdata.price_panel(["BTC", "eth"], days=5, use_cache=False)
    # plain symbols are suffixed with USDT and upper-cased
    assert "BTCUSDT" in seen
    assert "ETHUSDT" in seen


def test_price_panel_skips_empty_series(monkeypatch, tmp_path):
    monkeypatch.setattr(marketdata, "CACHE", tmp_path)

    def fake_fetch(symbol, *, days=120, **kwargs):
        if symbol.startswith("BAD"):
            return pd.Series(dtype="float64")
        return _synthetic_series(24)

    monkeypatch.setattr(marketdata, "fetch_binance_hourly", fake_fetch)
    df = marketdata.price_panel(["BTC", "BADCOIN"], days=5, use_cache=False)
    # the empty (bad) symbol is dropped, the good one remains
    assert "BTC" in df.columns
    assert "BADCOIN" not in df.columns
