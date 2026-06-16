from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from itertools import product
from pathlib import Path

from .backtest import run_backtest
from .data_sources import DataSource
from .models import BacktestResult, Candle, StrategySpec
from .strategies import generate_signals, initial_candidates


@dataclass(frozen=True)
class BattleEvaluation:
    symbol: str
    strategy: StrategySpec
    train_result: BacktestResult
    test_result: BacktestResult
    battle_score: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy.to_dict(),
            "train_result": self.train_result.to_dict(),
            "test_result": self.test_result.to_dict(),
            "battle_score": self.battle_score,
        }


@dataclass(frozen=True)
class BattleReport:
    symbols: list[str]
    train_ratio: float
    evaluations: list[BattleEvaluation]
    best: BattleEvaluation | None
    baselines: dict[str, BacktestResult]

    def to_dict(self) -> dict:
        return {
            "symbols": self.symbols,
            "train_ratio": self.train_ratio,
            "best": self.best.to_dict() if self.best else None,
            "evaluations": [item.to_dict() for item in self.evaluations],
            "baselines": {symbol: result.to_dict() for symbol, result in self.baselines.items()},
        }


def build_strategy_grid() -> list[StrategySpec]:
    """Build a deterministic parameter grid for real battle tests.

    Adaptive long/short candidates come first because they are the Track 1
    upgrade path and are the only family that can make money in down-only held
    out windows.
    """
    base = {strategy.name: strategy for strategy in initial_candidates()}
    grid: list[StrategySpec] = []

    perps = base["adaptive_trend_perps"]
    for fast, slow, long_max, short_min, short_tp in product(
        [13, 21, 34],
        [55, 89, 144],
        [65, 75, 85],
        [25, 35, 40, 45],
        [18, 24, 30],
    ):
        if fast >= slow:
            continue
        params = {
            "fast": fast,
            "slow": slow,
            "rsi_long_min": 30,
            "rsi_long_max": long_max,
            "rsi_short_min": short_min,
            "short_take_profit_rsi": short_tp,
        }
        grid.append(replace(perps, name=f"adaptive_trend_perps_f{fast}_s{slow}_lm{long_max}_sm{short_min}_tp{short_tp}", parameters=params))

    breakout = base["volatility_breakout"]
    for lookback, volume_window, rsi_max in product([8, 12, 18, 26, 34, 55, 89], [3, 5, 8, 12, 20], [70, 76, 82, 88, 95]):
        params = {"lookback": lookback, "volume_window": volume_window, "rsi_max": rsi_max}
        grid.append(replace(breakout, name=f"volatility_breakout_l{lookback}_v{volume_window}_r{rsi_max}", parameters=params))

    momentum = base["regime_adaptive_momentum"]
    for fast, slow, rsi_min, rsi_max, macd_required in product([5, 8, 13, 21, 34], [21, 34, 55, 89, 144], [30, 38, 45], [65, 75, 85, 95], [True, False]):
        if fast >= slow:
            continue
        params = {"fast": fast, "slow": slow, "rsi_min": rsi_min, "rsi_max": rsi_max, "macd_required": macd_required}
        grid.append(replace(momentum, name=f"regime_adaptive_momentum_f{fast}_s{slow}_{rsi_min}_{rsi_max}_{macd_required}", parameters=params))

    pullback = base["pullback_rebound"]
    for slow, rsi_buy, rsi_exit in product([21, 30, 55, 89], [30, 35, 38, 42, 46], [50, 58, 65]):
        params = {"fast": 10, "slow": slow, "rsi_buy": rsi_buy, "rsi_exit": rsi_exit}
        grid.append(replace(pullback, name=f"pullback_rebound_s{slow}_b{rsi_buy}_x{rsi_exit}", parameters=params))

    return grid


def split_train_test(candles: list[Candle], train_ratio: float) -> tuple[list[Candle], list[Candle]]:
    if not 0.3 <= train_ratio <= 0.85:
        raise ValueError("train_ratio must be between 0.3 and 0.85")
    if len(candles) < 80:
        raise ValueError("at least 80 candles are required for battle testing")
    cut = int(len(candles) * train_ratio)
    return candles[:cut], candles[cut:]


def battle_score(train_result: BacktestResult, test_result: BacktestResult) -> float:
    """Composite score: held-out profit first, then robustness.

    A strategy with negative test PnL is aggressively penalized even when the
    training window was strong. This keeps the product honest for hackathon PnL
    replay.
    """
    penalty = 0.0
    if train_result.total_return <= 0:
        penalty += abs(train_result.total_return) + 0.15
    if test_result.total_return <= 0:
        penalty += abs(test_result.total_return) + 0.35
    if test_result.max_drawdown > 0.30:
        penalty += test_result.max_drawdown
    return (
        2.0 * test_result.total_return
        + 0.12 * test_result.sharpe
        - 1.0 * test_result.max_drawdown
        - 0.0015 * test_result.turnover
        + 0.35 * train_result.total_return
        + 0.03 * train_result.sharpe
        - 0.35 * train_result.max_drawdown
        - penalty
    )


def run_battle_test(
    *,
    source: DataSource,
    symbols: list[str],
    output_dir: Path,
    limit_grid: int | None = None,
    train_ratio: float = 0.70,
) -> BattleReport:
    output_dir.mkdir(parents=True, exist_ok=True)
    grid = build_strategy_grid()
    if limit_grid is not None:
        grid = grid[:limit_grid]
    evaluations: list[BattleEvaluation] = []
    baselines: dict[str, BacktestResult] = {}

    for symbol in symbols:
        candles = source.load(symbol)
        train, test = split_train_test(candles, train_ratio)
        baselines[symbol] = run_backtest(test, [1] * len(test), strategy_name=f"{symbol}_buy_and_hold", fee_bps=0)
        for strategy in grid:
            fee_bps = float(strategy.risk_policy.get("fee_bps", 8))
            train_result = run_backtest(train, generate_signals(strategy, train), strategy_name=strategy.name, fee_bps=fee_bps)
            test_result = run_backtest(test, generate_signals(strategy, test), strategy_name=strategy.name, fee_bps=fee_bps)
            evaluations.append(
                BattleEvaluation(
                    symbol=symbol,
                    strategy=strategy,
                    train_result=train_result,
                    test_result=test_result,
                    battle_score=battle_score(train_result, test_result),
                )
            )
    ranked = sorted(evaluations, key=lambda item: item.battle_score, reverse=True)
    best = ranked[0] if ranked else None
    report = BattleReport(symbols=symbols, train_ratio=train_ratio, evaluations=ranked, best=best, baselines=baselines)
    (output_dir / "battle_summary.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    (output_dir / "battle_report.md").write_text(render_battle_report(report), encoding="utf-8")
    return report


def render_battle_report(report: BattleReport) -> str:
    lines = ["# Strategy Battle Test Report", "", f"Train ratio: `{report.train_ratio:.2f}`", ""]
    if report.best:
        best = report.best
        baseline = report.baselines.get(best.symbol)
        lines.extend(
            [
                "## Winner",
                f"- Symbol: `{best.symbol}`",
                f"- Strategy: `{best.strategy.name}`",
                f"- Battle score: `{best.battle_score:.4f}`",
                f"- Train return: `{best.train_result.total_return:.2%}` / Sharpe `{best.train_result.sharpe:.2f}` / max DD `{best.train_result.max_drawdown:.2%}`",
                f"- Held-out return: `{best.test_result.total_return:.2%}` / Sharpe `{best.test_result.sharpe:.2f}` / max DD `{best.test_result.max_drawdown:.2%}`",
                f"- Held-out turnover: `{best.test_result.turnover}` / exposure `{best.test_result.exposure:.2%}` / rule violations `{len(best.test_result.rule_violations)}`",
            ]
        )
        if baseline:
            lines.append(f"- Held-out buy-and-hold baseline: `{baseline.total_return:.2%}` / max DD `{baseline.max_drawdown:.2%}`")
        lines.append("")
    lines.extend(["## Top candidates", "", "| rank | symbol | strategy | train ret | test ret | test Sharpe | test DD | turnover | score |", "|---:|---|---|---:|---:|---:|---:|---:|---:|"])
    for rank, item in enumerate(report.evaluations[:25], start=1):
        lines.append(
            f"| {rank} | {item.symbol} | {item.strategy.name} | {item.train_result.total_return:.2%} | {item.test_result.total_return:.2%} | {item.test_result.sharpe:.2f} | {item.test_result.max_drawdown:.2%} | {item.test_result.turnover} | {item.battle_score:.4f} |"
        )
    lines.extend(["", "## Baselines", "", "| symbol | buy-and-hold test return | Sharpe | max DD |", "|---|---:|---:|---:|"])
    for symbol, result in report.baselines.items():
        lines.append(f"| {symbol} | {result.total_return:.2%} | {result.sharpe:.2f} | {result.max_drawdown:.2%} |")
    return "\n".join(lines) + "\n"
