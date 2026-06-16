from __future__ import annotations

import os
from typing import Any

try:  # optional on-chain dependency
    from web3 import Web3
except ImportError:  # pragma: no cover - exercised only when web3 is absent
    Web3 = None  # type: ignore[assignment]

COMPETITION_REGISTRY = "0x212c61b9b72c95d95bf29cf032f5e5635629aed5"
BSC_CHAIN_ID = 56
DEFAULT_BSC_RPC_URL = "https://bsc-dataseed.binance.org"
REGISTRATION_DEADLINE_TS = 1782345600  # 2026-06-25 00:00 UTC (on-chain value)

# Minimal ABI for the four functions plus the Registered event.
REGISTRY_ABI: list[dict[str, Any]] = [
    {
        "name": "register",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [],
        "outputs": [],
    },
    {
        "name": "isRegistered",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "registrationStart",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "registrationDeadline",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "Registered",
        "type": "event",
        "anonymous": False,
        "inputs": [{"name": "account", "type": "address", "indexed": True}],
    },
]


def _require_web3() -> None:
    if Web3 is None:
        raise RuntimeError(
            "web3 is required for on-chain actions; install it (e.g. `pip install web3>=6`) "
            "or use the 'onchain' extra."
        )


def _rpc(rpc_url: str | None) -> str:
    return rpc_url or os.environ.get("BSC_RPC_URL", DEFAULT_BSC_RPC_URL)


def _contract(rpc_url: str | None):
    _require_web3()
    w3 = Web3(Web3.HTTPProvider(_rpc(rpc_url)))
    address = Web3.to_checksum_address(COMPETITION_REGISTRY)
    return w3, w3.eth.contract(address=address, abi=REGISTRY_ABI)


def is_window_open(start: int, deadline: int, now_ts: int) -> bool:
    """Pure helper: is ``now_ts`` within the inclusive [start, deadline] window."""
    return start <= now_ts <= deadline


def registration_window(rpc_url: str | None = None) -> dict[str, int]:
    """Read-only: fetch the on-chain registration start/deadline timestamps."""
    _, contract = _contract(rpc_url)
    return {
        "start": int(contract.functions.registrationStart().call()),
        "deadline": int(contract.functions.registrationDeadline().call()),
    }


def is_registered(address: str, rpc_url: str | None = None) -> bool:
    """Read-only: whether ``address`` is already registered."""
    _require_web3()
    _, contract = _contract(rpc_url)
    checksummed = Web3.to_checksum_address(address)
    return bool(contract.functions.isRegistered(checksummed).call())


def register_agent(
    *,
    dry_run: bool = True,
    rpc_url: str | None = None,
    private_key_env: str = "AGENT_PRIVATE_KEY",
) -> dict[str, Any]:
    """Register the agent on the CompetitionRegistry.

    On ``dry_run`` (default) returns the unsigned ``register()`` transaction dict.
    Otherwise signs with the key from ``private_key_env`` and broadcasts, waiting
    for the receipt. Requires web3 for either path (tx building needs it).

    The private key is read from the environment and is never logged.
    """
    _require_web3()
    w3, contract = _contract(rpc_url)

    private_key = os.environ.get(private_key_env)
    if not private_key:
        raise RuntimeError(
            f"missing private key: set the {private_key_env} environment variable"
        )

    account = w3.eth.account.from_key(private_key)
    sender = account.address

    tx = contract.functions.register().build_transaction(
        {
            "from": sender,
            "chainId": BSC_CHAIN_ID,
            "nonce": w3.eth.get_transaction_count(sender),
        }
    )

    if dry_run:
        return {"unsigned_tx": tx, "from": sender, "registry": COMPETITION_REGISTRY}

    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return {
        "tx_hash": tx_hash.hex(),
        "from": sender,
        "registry": COMPETITION_REGISTRY,
        "status": int(receipt["status"]),
        "block_number": int(receipt["blockNumber"]),
    }
