from datetime import datetime, timedelta, timezone
from pathlib import Path

from bnbhack_agent.battle import build_strategy_grid, run_battle_test
from bnbhack_agent.data_sources import FixtureDataSource
from bnbhack_agent.models import Candle
from bnbhack_agent.strategies import generate_signals, initial_candidates


class InlineDataSource:
    def __init__(self, candles):
        self._candles = candles

    def load(self, symbol: str):
        return self._candles


def synthetic_trend_candles():
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    candles = []
    for i in range(220):
        # Strong early uptrend, then a persistent downtrend so the perps strategy
        # has to prove it can short held-out weakness.
        drift = 0.008 if i < 120 else -0.010
        open_price = price
        close = max(10, price * (1 + drift))
        candles.append(
            Candle(
                timestamp=base + timedelta(days=i),
                open=open_price,
                high=max(open_price, close) * 1.01,
                low=min(open_price, close) * 0.99,
                close=close,
                volume=1_000_000 + i * 1000,
            )
        )
        price = close
    return candles


def test_adaptive_perps_strategy_can_short_downtrend():
    candles = synthetic_trend_candles()
    candidate = next(strategy for strategy in initial_candidates() if strategy.name == "adaptive_trend_perps")
    signals = generate_signals(candidate, candles)
    assert -1 in signals
    assert all(signal in {-1, 0, 1} for signal in signals)


def test_build_strategy_grid_includes_track1_upgrade_perps_candidates():
    grid = build_strategy_grid()
    names = [strategy.name for strategy in grid]
    assert any(name.startswith("adaptive_trend_perps") for name in names)
    assert len(grid) >= 50


def test_battle_test_writes_profitable_out_of_sample_report(tmp_path):
    source = InlineDataSource(synthetic_trend_candles())
    report = run_battle_test(
        source=source,
        symbols=["BNB"],
        output_dir=tmp_path,
        limit_grid=120,
        train_ratio=0.65,
    )

    assert report.best is not None
    assert report.best.test_result.total_return > 0
    assert report.best.test_result.rule_violations == []
    assert (tmp_path / "battle_report.md").exists()
    assert (tmp_path / "battle_summary.json").exists()


def test_fixture_data_still_runs_battle_without_errors(tmp_path):
    report = run_battle_test(
        source=FixtureDataSource(Path("data/sample_bnb_ohlcv.csv")),
        symbols=["BNB"],
        output_dir=tmp_path,
        limit_grid=30,
        train_ratio=0.65,
    )
    assert report.evaluations
