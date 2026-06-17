"""Negative-news veto: fires on a severe held-token event, graceful otherwise, TTL-cached."""
from __future__ import annotations

import bnbhack_agent.news_veto as NV


def _patch(monkeypatch, scores):
    """scores: symbol -> verdict dict (or None). Bypasses network (twitter + M3)."""
    monkeypatch.setattr(NV, "_fresh_social", lambda client, sym, cfg: f"news about {sym}")
    monkeypatch.setattr(NV, "_score_event", lambda sym, social, cfg: scores.get(sym))


def test_veto_fires_on_severe_event(monkeypatch, tmp_path):
    _patch(monkeypatch, {
        "STG": {"negative_event": True, "category": "delisting", "severity": 8, "reason": "Coinbase delist"},
        "ETH": {"negative_event": False, "severity": 0},
        "XRP": {"negative_event": True, "category": "chatter", "severity": 3},  # below threshold -> ignored
    })
    cfg = NV.VetoConfig(cache_path=tmp_path / "nv.json")
    vetoed, audit = NV.negative_vetoes(object(), ["ETH", "STG", "XRP"], cfg)
    assert vetoed == {"STG"}
    assert audit and audit[0]["symbol"] == "STG" and audit[0]["severity"] == 8


def test_no_veto_when_unavailable(monkeypatch, tmp_path):
    # M3/social unavailable -> _score_event returns None -> never block, never veto
    _patch(monkeypatch, {})
    vetoed, audit = NV.negative_vetoes(object(), ["ETH", "STG"], NV.VetoConfig(cache_path=tmp_path / "nv.json"))
    assert vetoed == set() and audit == []


def test_bounded_to_max_checks(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(NV, "_fresh_social", lambda client, sym, cfg: (calls.append(sym), "x")[1])
    monkeypatch.setattr(NV, "_score_event", lambda sym, social, cfg: None)
    cfg = NV.VetoConfig(cache_path=tmp_path / "nv.json", max_checks=3)
    NV.negative_vetoes(object(), [f"T{i}" for i in range(10)], cfg)
    assert len(calls) == 3  # only the held sleeve, capped
