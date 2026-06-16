from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class TWAKAdapter:
    """Thin Trust Wallet Agent Kit CLI adapter.

    The demo uses `quote_only=True` by default. Real execution requires TWAK
    credentials/wallet configured by the official installer.
    """

    command: str = "twak"

    def available(self) -> bool:
        return shutil.which(self.command) is not None

    def quote_swap(self, amount: float, from_asset: str, to_asset: str, *, chain: str = "bsc") -> str:
        if not self.available():
            raise RuntimeError("twak CLI not found; install from https://agent-kit.trustwallet.com/install.sh")
        cmd = [self.command, "swap", str(amount), from_asset.upper(), to_asset.upper(), "--quote-only", "--chain", chain]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return result.stdout.strip()

    def wallet_portfolio(self) -> str:
        if not self.available():
            raise RuntimeError("twak CLI not found; install from https://agent-kit.trustwallet.com/install.sh")
        result = subprocess.run([self.command, "wallet", "portfolio"], check=True, capture_output=True, text=True)
        return result.stdout.strip()
