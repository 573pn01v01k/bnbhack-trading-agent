from bnbhack_agent.indicators import ema, macd, rsi, sma


def test_sma_returns_none_until_window_is_available():
    assert sma([1, 2, 3, 4], 3) == [None, None, 2.0, 3.0]


def test_ema_tracks_latest_values_more_than_old_values():
    values = ema([10, 10, 10, 20], 3)
    assert values[-1] > values[-2]
    assert round(values[-1], 2) == 15.0


def test_rsi_is_high_for_monotonic_uptrend():
    values = rsi([1, 2, 3, 4, 5, 6, 7], 3)
    assert values[-1] == 100.0


def test_macd_emits_histogram_series_with_same_length():
    line, signal, hist = macd(list(range(1, 40)), fast=5, slow=8, signal_period=4)
    assert len(line) == 39
    assert len(signal) == 39
    assert len(hist) == 39
    assert hist[-1] is not None
