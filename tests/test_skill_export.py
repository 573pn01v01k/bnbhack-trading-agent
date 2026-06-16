from pathlib import Path

from bnbhack_agent.cmc_skill import export_cmc_skill_spec
from bnbhack_agent.data_sources import FixtureDataSource
from bnbhack_agent.research_loop import AutoResearchLoop


def test_exported_skill_spec_contains_hackathon_requirements(tmp_path):
    summary = AutoResearchLoop(FixtureDataSource(Path("data/sample_bnb_ohlcv.csv")), "BNB", 1, tmp_path).run()
    spec = export_cmc_skill_spec(summary, include_monolit=True)

    assert "CoinMarketCap" in spec
    assert "backtestable" in spec.lower()
    assert "risk" in spec.lower()
    assert "Monolit MCP" in spec
    assert "Trust Wallet Agent Kit" in spec
