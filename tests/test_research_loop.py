from pathlib import Path

from bnbhack_agent.data_sources import FixtureDataSource
from bnbhack_agent.research_loop import AutoResearchLoop


def test_research_loop_selects_best_candidate_and_writes_artifacts(tmp_path):
    source = FixtureDataSource(Path("data/sample_bnb_ohlcv.csv"))
    loop = AutoResearchLoop(data_source=source, symbol="BNB", iterations=2, output_dir=tmp_path)
    summary = loop.run()

    assert summary.best.strategy.name
    assert summary.best.result.score == max(item.result.score for item in summary.evaluations)
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "report.md").exists()
    assert "propose" in summary.loop_trace[0].phase
    assert any("critique" in step.phase for step in summary.loop_trace)
