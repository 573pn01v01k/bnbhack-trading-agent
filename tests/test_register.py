from __future__ import annotations

import pytest

from bnbhack_agent import register
from bnbhack_agent.register import (
    BSC_CHAIN_ID,
    COMPETITION_REGISTRY,
    REGISTRATION_DEADLINE_TS,
    REGISTRY_ABI,
    is_window_open,
    register_agent,
)


def test_constants():
    assert COMPETITION_REGISTRY == "0x212c61b9b72c95d95bf29cf032f5e5635629aed5"
    assert BSC_CHAIN_ID == 56
    assert REGISTRATION_DEADLINE_TS == 1782345600


def test_abi_exposes_expected_members():
    names = {entry["name"] for entry in REGISTRY_ABI}
    assert {"register", "isRegistered", "registrationStart", "registrationDeadline", "Registered"} <= names
    register_fn = next(e for e in REGISTRY_ABI if e["name"] == "register")
    assert register_fn["inputs"] == []
    assert register_fn["stateMutability"] == "nonpayable"
    event = next(e for e in REGISTRY_ABI if e["name"] == "Registered")
    assert event["type"] == "event"
    assert event["inputs"][0]["indexed"] is True


def test_is_window_open_boundaries():
    start, deadline = 100, 200
    assert is_window_open(start, deadline, 100) is True
    assert is_window_open(start, deadline, 150) is True
    assert is_window_open(start, deadline, 200) is True
    assert is_window_open(start, deadline, 99) is False
    assert is_window_open(start, deadline, 201) is False


def test_register_agent_requires_web3_or_builds_tx(monkeypatch):
    monkeypatch.setenv("AGENT_PRIVATE_KEY", "0x" + "11" * 32)
    if register.Web3 is None:
        with pytest.raises(RuntimeError, match="web3 is required"):
            register_agent(dry_run=True)
    else:  # pragma: no cover - only when web3 is installed
        # Avoid real network: stub the contract/web3 building path.
        class _Fns:
            def register(self):
                class _Tx:
                    def build_transaction(self, params):
                        return {**params, "data": "0x1249c58b"}

                return _Tx()

        class _Contract:
            functions = _Fns()

        class _W3:
            class eth:
                @staticmethod
                def get_transaction_count(_addr):
                    return 0

                class account:
                    @staticmethod
                    def from_key(_pk):
                        class _Acct:
                            address = "0x000000000000000000000000000000000000dEaD"

                        return _Acct()

        monkeypatch.setattr(register, "_contract", lambda rpc_url: (_W3(), _Contract()))
        out = register_agent(dry_run=True)
        assert "unsigned_tx" in out
        assert out["unsigned_tx"]["chainId"] == BSC_CHAIN_ID
        assert out["registry"] == COMPETITION_REGISTRY


def test_read_helpers_require_web3_when_absent():
    if register.Web3 is None:
        with pytest.raises(RuntimeError, match="web3 is required"):
            register.registration_window()
        with pytest.raises(RuntimeError, match="web3 is required"):
            register.is_registered("0x000000000000000000000000000000000000dEaD")
