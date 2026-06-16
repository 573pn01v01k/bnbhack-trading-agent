from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .backtest import run_backtest
from .data_sources import DataSource, MonolitMCPEnrichmentSource
from .models import BacktestResult, Evaluation, LoopStep, ResearchSummary, StrategySpec
from .strategies import generate_signals, initial_candidates, mutate_strategy


@dataclass
class AutoResearchLoop:
    data_source: DataSource
    symbol: str = "BNB"
    iterations: int = 3
    output_dir: Path = Path("runs/demo")
    use_monolit: bool = False

    def run(self) -> ResearchSummary:
        candles = self.data_source.load(self.symbol)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        features = MonolitMCPEnrichmentSource().load_features(self.symbol, candles) if self.use_monolit else {}
        candidates = initial_candidates()
        evaluations: list[Evaluation] = []
        trace: list[LoopStep] = [LoopStep("propose", f"Seeded {len(candidates)} candidate strategies for {self.symbol}.", 0)]
        seen: set[tuple[str, tuple[tuple[str, object], ...]]] = set()
        for iteration in range(1, self.iterations + 1):
            trace.append(LoopStep("backtest", f"Evaluating {len(candidates)} candidates on {len(candles)} candles.", iteration))
            current_round: list[Evaluation] = []
            for strategy in candidates:
                key = (strategy.name, tuple(sorted(strategy.parameters.items())))
                if key in seen:
                    continue
                seen.add(key)
                signals = generate_signals(strategy, candles, features)
                fee_bps = float(strategy.risk_policy.get("fee_bps", 8))
                result = run_backtest(candles, signals, strategy_name=strategy.name, fee_bps=fee_bps)
                critique = critique_result(strategy, result)
                evaluation = Evaluation(strategy=strategy, result=result, critique=critique, iteration=iteration)
                evaluations.append(evaluation)
                current_round.append(evaluation)
            if not current_round:
                break
            round_best = max(current_round, key=lambda item: item.result.score)
            trace.append(LoopStep("critique", round_best.critique, iteration))
            candidates = [mutate_strategy(round_best.strategy, round_best.critique, iteration)]
            global_best = max(evaluations, key=lambda item: item.result.score)
            if global_best.strategy.name != round_best.strategy.name:
                candidates.append(mutate_strategy(global_best.strategy, global_best.critique, iteration))
            trace.append(LoopStep("mutate", f"Generated {len(candidates)} refined candidate(s) from best score {round_best.result.score:.4f}.", iteration))
        best = max(evaluations, key=lambda item: item.result.score)
        summary = ResearchSummary(symbol=self.symbol, best=best, evaluations=evaluations, loop_trace=trace, data_points=len(candles))
        self._write_artifacts(summary)
        return summary

    def _write_artifacts(self, summary: ResearchSummary) -> None:
        (self.output_dir / "summary.json").write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
        (self.output_dir / "report.md").write_text(render_report(summary), encoding="utf-8")


def critique_result(strategy: StrategySpec, result: BacktestResult) -> str:
    max_dd_allowed = float(strategy.risk_policy.get("max_drawdown", 0.25))
    target_exposure = float(strategy.risk_policy.get("target_exposure", 0.45))
    if result.rule_violations:
        return f"Rule adherence issue: {len(result.rule_violations)} signal violations; clamp or simplify exposure."
    if result.max_drawdown > max_dd_allowed:
        return f"Drawdown {result.max_drawdown:.2%} exceeds policy {max_dd_allowed:.2%}; slow entries and tighten RSI ceiling."
    if result.exposure < target_exposure * 0.45:
        return f"Too little exposure ({result.exposure:.2%}); relax entry thresholds without increasing max position."
    if result.turnover > result.periods * 0.22:
        return f"Turnover is high ({result.turnover}); smooth signals to reduce fees and whipsaw."
    if result.total_return < 0:
        return f"Negative return {result.total_return:.2%}; change regime filter and search for stronger trend confirmation."
    return f"Candidate is viable: return {result.total_return:.2%}, Sharpe {result.sharpe:.2f}, max drawdown {result.max_drawdown:.2%}; refine for robustness."


def render_report(summary: ResearchSummary) -> str:
    best = summary.best
    lines = [
        f"# AutoResearch Loop Report — {summary.symbol}",
        "",
        "## Winning strategy",
        f"- Name: `{best.strategy.name}`",
        f"- Score: `{best.result.score:.4f}`",
        f"- Total return: `{best.result.total_return:.2%}`",
        f"- Sharpe: `{best.result.sharpe:.2f}`",
        f"- Max drawdown: `{best.result.max_drawdown:.2%}`",
        f"- Turnover: `{best.result.turnover}`",
        f"- Exposure: `{best.result.exposure:.2%}`",
        "",
        "## AutoResearch trace",
    ]
    for step in summary.loop_trace:
        lines.append(f"- Iteration {step.iteration} / **{step.phase}** — {step.message}")
    lines.extend(["", "## Candidate table", "", "| iter | strategy | return | sharpe | max DD | turnover | score | critique |", "|---:|---|---:|---:|---:|---:|---:|---|"])
    for item in sorted(summary.evaluations, key=lambda x: x.result.score, reverse=True):
        lines.append(
            f"| {item.iteration} | {item.strategy.name} | {item.result.total_return:.2%} | {item.result.sharpe:.2f} | {item.result.max_drawdown:.2%} | {item.result.turnover} | {item.result.score:.4f} | {item.critique} |"
        )
    return "\n".join(lines) + "\n"
