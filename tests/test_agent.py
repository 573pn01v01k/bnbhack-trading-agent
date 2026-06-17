"""Agent heartbeat: the contest requires >=1 trade/day. When nothing trades and the
agent has been idle past the heartbeat window, it must force a tiny stable rotation."""
from __future__ import annotations

from bnbhack_agent import agent as A


# diversified target (each within the per-trade risk cap), summing to < 1 (rest cash)
_WEIGHTS = {s: 0.1 for s in ("ETH", "XRP", "ADA", "DOGE", "TRX", "UNI", "LINK", "ZEC")}


def _fixed_alloc(cfg, client=None):
    return {"weights": dict(_WEIGHTS), "as_of": "2026-06-17T00:00:00Z",
            "risk_off_fraction": 0.0, "vetoes": [], "flow_imbalance": {}}


def test_heartbeat_fires_when_idle(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(A, "LOG_FILE", tmp_path / "log.jsonl")
    monkeypatch.setattr(A, "decide", _fixed_alloc)
    # holdings already equal the target (0.1 * 500 = 50 each) -> no normal trades; idle since epoch
    A.AgentState(last_trade_ts=0.0, holdings={s: 50.0 for s in _WEIGHTS}).save()

    rec = A.run_once(A.AgentConfig(use_monolit_edge=False, capital_usd=500.0), client=None, live=False)

    assert rec["heartbeat"] is True
    assert any(e.get("heartbeat") for e in rec["executed"]), "a heartbeat trade must be recorded"


def test_no_heartbeat_when_already_trading(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(A, "LOG_FILE", tmp_path / "log.jsonl")
    monkeypatch.setattr(A, "decide", _fixed_alloc)
    A.AgentState(last_trade_ts=0.0, holdings={}).save()  # empty -> real buys happen this cycle

    rec = A.run_once(A.AgentConfig(use_monolit_edge=False, capital_usd=500.0), client=None, live=False)

    assert rec["heartbeat"] is False
    assert len([e for e in rec["executed"] if not e.get("heartbeat")]) >= 1
