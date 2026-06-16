from __future__ import annotations

import argparse
from pathlib import Path

from .battle import run_battle_test
from .cmc_skill import save_cmc_skill_spec
from .data_sources import BinanceKlinesSource, CMCDataSource, FixtureDataSource
from .research_loop import AutoResearchLoop


def _source(name: str, data_path: Path, count: int):
    if name == "fixture":
        return FixtureDataSource(data_path)
    if name == "cmc":
        return CMCDataSource(count=count)
    if name == "binance":
        return BinanceKlinesSource(limit=count)
    raise ValueError(f"unknown source: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BNB Hack AutoResearch strategy agent")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("research", help="run propose/backtest/critique/mutate loop")
    run.add_argument("--symbol", default="BNB")
    run.add_argument("--source", choices=["fixture", "cmc", "binance"], default="fixture")
    run.add_argument("--data", type=Path, default=Path("data/sample_bnb_ohlcv.csv"))
    run.add_argument("--count", type=int, default=180)
    run.add_argument("--iterations", type=int, default=3)
    run.add_argument("--out", type=Path, default=Path("runs/demo"))
    run.add_argument("--use-monolit", action="store_true")
    run.add_argument("--export-skill", action="store_true")

    demo = sub.add_parser("demo", help="run local sample loop and export CMC Skill spec")
    demo.add_argument("--out", type=Path, default=Path("runs/demo"))

    battle = sub.add_parser("battle", help="run grid battle tests with train/test split")
    battle.add_argument("--symbols", default="BNB", help="comma-separated symbols, e.g. BNB,BTC,ETH")
    battle.add_argument("--source", choices=["fixture", "cmc", "binance"], default="binance")
    battle.add_argument("--data", type=Path, default=Path("data/sample_bnb_ohlcv.csv"))
    battle.add_argument("--count", type=int, default=1000)
    battle.add_argument("--out", type=Path, default=Path("runs/battle"))
    battle.add_argument("--limit-grid", type=int, default=None)
    battle.add_argument("--train-ratio", type=float, default=0.70)

    args = parser.parse_args(argv)
    if args.command == "demo":
        summary = AutoResearchLoop(FixtureDataSource(Path("data/sample_bnb_ohlcv.csv")), "BNB", 3, args.out).run()
        spec_path = save_cmc_skill_spec(summary, args.out / "cmc_strategy_skill.md", include_monolit=True)
        print(f"best={summary.best.strategy.name} return={summary.best.result.total_return:.2%} sharpe={summary.best.result.sharpe:.2f} max_dd={summary.best.result.max_drawdown:.2%}")
        print(f"wrote {args.out / 'summary.json'}")
        print(f"wrote {args.out / 'report.md'}")
        print(f"wrote {spec_path}")
        return 0
    if args.command == "research":
        source = _source(args.source, args.data, args.count)
        summary = AutoResearchLoop(source, args.symbol, args.iterations, args.out, use_monolit=args.use_monolit).run()
        print(f"best={summary.best.strategy.name} score={summary.best.result.score:.4f} return={summary.best.result.total_return:.2%} max_dd={summary.best.result.max_drawdown:.2%}")
        if args.export_skill:
            spec_path = save_cmc_skill_spec(summary, args.out / "cmc_strategy_skill.md", include_monolit=args.use_monolit)
            print(f"wrote {spec_path}")
        return 0
    if args.command == "battle":
        source = _source(args.source, args.data, args.count)
        symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
        report = run_battle_test(
            source=source,
            symbols=symbols,
            output_dir=args.out,
            limit_grid=args.limit_grid,
            train_ratio=args.train_ratio,
        )
        if report.best:
            best = report.best
            print(
                f"best={best.strategy.name} symbol={best.symbol} "
                f"test_return={best.test_result.total_return:.2%} "
                f"test_sharpe={best.test_result.sharpe:.2f} "
                f"test_max_dd={best.test_result.max_drawdown:.2%}"
            )
        print(f"wrote {args.out / 'battle_summary.json'}")
        print(f"wrote {args.out / 'battle_report.md'}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
