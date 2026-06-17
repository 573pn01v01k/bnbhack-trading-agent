"""CMC Agent Hub overlay: neutral without a key, bounded exposure trim in euphoria."""
from __future__ import annotations

from bnbhack_agent.cmc import CMCClient, regime_signal


class _FakeCMC:
    def __init__(self, fng):
        self._fng = fng

    def available(self):
        return True

    def fear_greed(self):
        return self._fng

    def global_metrics(self):
        return {"btc_dominance": 55.0}


def test_neutral_without_key():
    assert CMCClient(api_key=None).available() is False
    assert regime_signal(None)["caution_factor"] == 1.0


def test_trims_in_greed_only():
    assert regime_signal(_FakeCMC(85))["caution_factor"] == 0.80   # extreme greed -> biggest trim
    assert regime_signal(_FakeCMC(72))["caution_factor"] == 0.90   # greed -> mild trim
    assert regime_signal(_FakeCMC(50))["caution_factor"] == 1.0    # neutral
    assert regime_signal(_FakeCMC(10))["caution_factor"] == 1.0    # extreme fear -> do NOT add risk
