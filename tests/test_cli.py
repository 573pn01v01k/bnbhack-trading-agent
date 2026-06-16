from pathlib import Path

from bnbhack_agent.cli import main


def test_cli_battle_fixture_command_writes_report(tmp_path):
    code = main([
        "battle",
        "--source",
        "fixture",
        "--symbols",
        "BNB",
        "--out",
        str(tmp_path),
        "--limit-grid",
        "20",
        "--train-ratio",
        "0.65",
    ])
    assert code == 0
    assert (tmp_path / "battle_report.md").exists()
    assert (tmp_path / "battle_summary.json").exists()
