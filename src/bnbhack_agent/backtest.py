from __future__ import annotations

import math
from statistics import fmean, stdev

from .models import BacktestResult, Candle


def _max_drawdown(equity_curve: list[float]) -> float:
    peak = equity_curve[0]
    max_dd = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    return max_dd


def _sharpe(period_returns: list[float], annualization: float) -> float:
    if len(period_returns) < 2:
        return 0.0
    sigma = stdev(period_returns)
    if sigma == 0:
        return 0.0
    return fmean(period_returns) / sigma * math.sqrt(annualization)


def run_backtest(
    candles: list[Candle],
    signals: list[int | float],
    *,
    strategy_name: str = "anonymous",
    initial_cash: float = 10_000.0,
    fee_bps: float = 8.0,
    annualization: float = 365.0,
) -> BacktestResult:
    """Run a deterministic bar-by-bar backtest.

    Signal convention: `signals[i]` is the exposure used for the return from
    candle `i-1` to candle `i`, preventing lookahead in generated strategies.
    """
    violations: list[str] = []
    if len(candles) != len(signals):
        raise ValueError("candles and signals must have the same length")
    if len(candles) < 2:
        raise ValueError("at least two candles are required")
    clean_signals: list[float] = []
    for i, raw in enumerate(signals):
        signal = float(raw)
        if signal < -1 or signal > 1:
            violations.append(f"signal[{i}]={signal} outside [-1, 1]; clipped")
            signal = max(-1.0, min(1.0, signal))
        clean_signals.append(signal)
    equity = initial_cash
    equity_curve = [equity]
    period_returns: list[float] = []
    wins = 0
    turnover = 0
    for i in range(1, len(candles)):
        previous = clean_signals[i - 1]
        current = clean_signals[i]
        if current != previous:
            turnover += 1
        price_return = candles[i].close / candles[i - 1].close - 1
        fee = abs(current - previous) * (fee_bps / 10_000)
        period_return = current * price_return - fee
        equity *= 1 + period_return
        period_returns.append(period_return)
        equity_curve.append(equity)
        if period_return > 0:
            wins += 1
    total_return = equity / initial_cash - 1
    max_dd = _max_drawdown(equity_curve)
    sharpe = _sharpe(period_returns, annualization)
    exposure = sum(abs(x) for x in clean_signals[1:]) / (len(clean_signals) - 1)
    win_rate = wins / len(period_returns)
    score = total_return + 0.05 * sharpe - 0.75 * max_dd - 0.002 * turnover - 0.10 * len(violations)
    return BacktestResult(
        strategy_name=strategy_name,
        initial_cash=initial_cash,
        final_equity=equity,
        total_return=total_return,
        sharpe=sharpe,
        max_drawdown=max_dd,
        win_rate=win_rate,
        turnover=turnover,
        exposure=exposure,
        score=score,
        periods=len(period_returns),
        fee_bps=fee_bps,
        equity_curve=[round(x, 6) for x in equity_curve],
        period_returns=[round(x, 8) for x in period_returns],
        rule_violations=violations,
    )
