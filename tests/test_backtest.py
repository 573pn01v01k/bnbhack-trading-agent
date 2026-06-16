from datetime import datetime, timedelta, timezone

from bnbhack_agent.backtest import run_backtest
from bnbhack_agent.models import Candle


def candles_from_closes(closes):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(
            timestamp=base + timedelta(days=i),
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            volume=1000 + i,
        )
        for i, close in enumerate(closes)
    ]


def test_backtest_rewards_buy_and_hold_on_uptrend():
    candles = candles_from_closes([100, 102, 104, 108, 112])
    result = run_backtest(candles, [1, 1, 1, 1, 1], initial_cash=10_000, fee_bps=0)
    assert result.total_return > 0.11
    assert result.max_drawdown == 0
    assert result.rule_violations == []


def test_backtest_penalizes_drawdown_and_turnover():
    candles = candles_from_closes([100, 120, 80, 82, 81])
    result = run_backtest(candles, [1, 0, 1, 0, 1], initial_cash=10_000, fee_bps=10)
    assert result.max_drawdown > 0
    assert result.turnover == 4
    assert result.total_return < 0
