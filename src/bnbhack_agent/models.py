from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class StrategySpec:
    name: str
    description: str
    parameters: dict[str, float | int | str | bool]
    entry_rules: list[str]
    exit_rules: list[str]
    risk_policy: dict[str, float | int | str | bool]
    sponsor_capabilities: list[str]
    tags: list[str] = field(default_factory=list)
    monolit_enrichment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestResult:
    strategy_name: str
    initial_cash: float
    final_equity: float
    total_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    turnover: int
    exposure: float
    score: float
    periods: int
    fee_bps: float
    equity_curve: list[float]
    period_returns: list[float]
    rule_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Evaluation:
    strategy: StrategySpec
    result: BacktestResult
    critique: str
    iteration: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "strategy": self.strategy.to_dict(),
            "result": self.result.to_dict(),
            "critique": self.critique,
        }


@dataclass(frozen=True)
class LoopStep:
    phase: str
    message: str
    iteration: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchSummary:
    symbol: str
    best: Evaluation
    evaluations: list[Evaluation]
    loop_trace: list[LoopStep]
    data_points: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "data_points": self.data_points,
            "best": self.best.to_dict(),
            "evaluations": [item.to_dict() for item in self.evaluations],
            "loop_trace": [step.to_dict() for step in self.loop_trace],
        }
