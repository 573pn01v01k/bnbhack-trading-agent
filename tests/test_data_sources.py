from pathlib import Path

from bnbhack_agent.data_sources import FixtureDataSource, parse_cmc_ohlcv_response


def test_fixture_data_source_loads_sample_candles():
    candles = FixtureDataSource(Path("data/sample_bnb_ohlcv.csv")).load("BNB")
    assert len(candles) >= 90
    assert candles[0].close > 0


def test_parse_cmc_ohlcv_response_handles_cmc_shape():
    payload = {
        "data": {
            "quotes": [
                {"time_close": "2026-01-01T00:00:00.000Z", "quote": {"USD": {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}}},
                {"time_close": "2026-01-02T00:00:00.000Z", "quote": {"USD": {"open": 1.5, "high": 2.5, "low": 1.2, "close": 2.0, "volume": 120}}},
            ]
        }
    }
    candles = parse_cmc_ohlcv_response(payload)
    assert [c.close for c in candles] == [1.5, 2.0]
