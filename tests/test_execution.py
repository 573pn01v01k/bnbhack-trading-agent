from __future__ import annotations

import subprocess

import pytest

from bnbhack_agent.execution import RiskCaps, TWAKAdapter, check_trade_allowed


class _FakeCompleted:
    def __init__(self, stdout: str = "ok") -> None:
        self.stdout = stdout
        self.returncode = 0


@pytest.fixture
def captured(monkeypatch):
    """Pretend twak is installed; capture the argv passed to subprocess.run."""
    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return _FakeCompleted("stub-output")

    monkeypatch.setattr("bnbhack_agent.execution.shutil.which", lambda _c: "/usr/bin/twak")
    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_quote_swap_includes_quote_only_and_bsc(captured):
    out = TWAKAdapter().quote_swap(1.0, "bnb", "usdt")
    assert out == "stub-output"
    cmd = captured[0]
    assert "--quote-only" in cmd
    assert "--chain" in cmd and "bsc" in cmd
    assert cmd[:2] == ["twak", "swap"]
    # native BNB passes through as a symbol; long-tail/stable symbols resolve to a
    # BSC contract address (TWAK rejects bare BEP-20 symbols like USDT/CAKE).
    assert "BNB" in cmd
    assert "0x55d398326f99059ff775485246999027b3197955" in cmd  # USDT on BSC


def test_execute_swap_resolves_symbols_and_uses_usd():
    # The live path sizes in USD and must hand TWAK contract addresses, not symbols.
    cmd = TWAKAdapter().execute_swap(50.0, "USDT", "CAKE", chain="bsc")
    assert isinstance(cmd, list)
    assert "--usd" in cmd and "50.0" in cmd
    assert "0x55d398326f99059ff775485246999027b3197955" in cmd  # USDT
    assert "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82" in cmd  # CAKE
    assert "CAKE" not in cmd and "USDT" not in cmd               # no bare symbols


def test_execute_swap_dry_run_returns_command_without_running(monkeypatch):
    monkeypatch.delenv("TWAK_WALLET_PASSWORD", raising=False)

    def boom(*a, **k):  # pragma: no cover - must not be called on dry_run
        raise AssertionError("subprocess.run should not run on dry_run")

    monkeypatch.setattr(subprocess, "run", boom)
    cmd = TWAKAdapter().execute_swap(2.0, "bnb", "usdt", slippage_pct=0.5)
    assert isinstance(cmd, list)
    assert "--quote-only" not in cmd
    assert "--chain" in cmd and "bsc" in cmd
    assert "--slippage" in cmd and "0.5" in cmd
    assert "--password" not in cmd  # no env var set


def test_execute_swap_picks_up_password_env(monkeypatch):
    monkeypatch.setenv("TWAK_WALLET_PASSWORD", "s3cret")
    cmd = TWAKAdapter().execute_swap(1.0, "bnb", "usdt")
    assert "--password" in cmd
    assert "s3cret" in cmd


def test_execute_swap_live_runs_subprocess(captured):
    out = TWAKAdapter().execute_swap(1.0, "bnb", "usdt", dry_run=False)
    assert out == "stub-output"
    cmd = captured[0]
    assert "--quote-only" not in cmd


def test_x402_request_and_quote_commands(monkeypatch):
    cmd = TWAKAdapter().x402_request(
        "https://api.example/x", max_payment=1000, auto_approve=True
    )
    assert cmd[:3] == ["twak", "x402", "request"]
    assert "--prefer-network" in cmd and "bsc" in cmd
    assert "--max-payment" in cmd and "1000" in cmd
    assert "--yes" in cmd and "--auto-approve" in cmd


def test_x402_quote_is_readonly(captured):
    TWAKAdapter().x402_quote("https://api.example/x")
    cmd = captured[0]
    assert cmd[:3] == ["twak", "x402", "quote"]


def test_automate_dca_command():
    cmd = TWAKAdapter().automate_dca(0.1, "usdt", "bnb", "1d")
    assert cmd[:3] == ["twak", "automate", "add"]
    assert "--interval" in cmd and "1d" in cmd
    assert "--chain" in cmd and "bsc" in cmd


def test_automate_limit_command_and_validation():
    cmd = TWAKAdapter().automate_limit(0.1, "usdt", "bnb", 600.0, "below")
    assert "--price" in cmd and "600.0" in cmd
    assert "--condition" in cmd and "below" in cmd
    with pytest.raises(ValueError):
        TWAKAdapter().automate_limit(0.1, "usdt", "bnb", 600.0, "sideways")


def test_serve_command_argv():
    cmd = TWAKAdapter().serve_command(watch=True, rest=True, x402=True)
    assert cmd == ["twak", "serve", "--watch", "--rest", "--x402"]
    assert TWAKAdapter().serve_command(watch=False) == ["twak", "serve"]


def test_balance_command(captured):
    TWAKAdapter().balance()
    assert captured[0] == ["twak", "balance"]


def test_read_op_raises_when_twak_missing(monkeypatch):
    monkeypatch.setattr("bnbhack_agent.execution.shutil.which", lambda _c: None)
    with pytest.raises(RuntimeError, match="twak CLI not found"):
        TWAKAdapter().quote_swap(1.0, "bnb", "usdt")


# -- risk gate ---------------------------------------------------------------


def test_check_trade_allowed_normal():
    caps = RiskCaps()
    allowed, reason = check_trade_allowed(
        caps,
        current_drawdown=0.05,
        daily_loss=0.02,
        proposed_position_frac=0.10,
        slippage_pct=0.5,
    )
    assert allowed is True
    assert reason == "ok"


def test_check_trade_allowed_drawdown_blocks():
    caps = RiskCaps(hard_drawdown_stop=0.22)
    allowed, reason = check_trade_allowed(
        caps,
        current_drawdown=0.25,
        daily_loss=0.0,
        proposed_position_frac=0.10,
        slippage_pct=0.5,
    )
    assert allowed is False
    assert "drawdown" in reason


def test_check_trade_allowed_slippage_blocks():
    caps = RiskCaps(max_slippage_pct=1.0)
    allowed, reason = check_trade_allowed(
        caps,
        current_drawdown=0.0,
        daily_loss=0.0,
        proposed_position_frac=0.10,
        slippage_pct=2.5,
    )
    assert allowed is False
    assert "slippage" in reason


def test_check_trade_allowed_daily_loss_and_position():
    caps = RiskCaps(daily_loss_limit_frac=0.10, max_position_frac=0.25)
    blocked_daily, reason_daily = check_trade_allowed(
        caps,
        current_drawdown=0.0,
        daily_loss=0.10,
        proposed_position_frac=0.10,
        slippage_pct=0.5,
    )
    assert blocked_daily is False and "daily loss" in reason_daily

    blocked_pos, reason_pos = check_trade_allowed(
        caps,
        current_drawdown=0.0,
        daily_loss=0.0,
        proposed_position_frac=0.50,
        slippage_pct=0.5,
    )
    assert blocked_pos is False and "position" in reason_pos
