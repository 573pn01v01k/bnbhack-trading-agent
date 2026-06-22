from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_INSTALL_HINT = "twak CLI not found; install from https://agent-kit.trustwallet.com/install.sh"

_UNIVERSE_JSON = Path(__file__).resolve().parent / "data" / "universe_bsc.json"


@functools.lru_cache(maxsize=1)
def _bsc_address_map() -> dict[str, str]:
    """symbol (UPPER) -> BSC contract address, loaded once from the universe file."""
    try:
        data = json.loads(_UNIVERSE_JSON.read_text())
    except (OSError, ValueError):
        return {}
    return {t["symbol"].upper(): t["bsc_contract"] for t in data if t.get("bsc_contract")}


def resolve_bsc_asset(asset: str) -> str:
    """Map a token SYMBOL to its BSC contract address for TWAK.

    TWAK resolves majors (USDT, native BNB) by symbol but rejects long-tail BEP-20
    symbols (CAKE, ASTER, …) with TOKEN_NOT_FOUND — those must be passed as a 0x
    contract address. Pass through anything already a 0x address or an unknown
    symbol unchanged (so native BNB still routes by symbol)."""
    if asset[:2].lower() == "0x":
        return asset
    return _bsc_address_map().get(asset.upper(), asset.upper())


@dataclass(frozen=True)
class TWAKAdapter:
    """Thin Trust Wallet Agent Kit CLI adapter.

    Read ops (quote, portfolio, balance, x402 quote) need no password. Signing
    ops (executing a swap, x402 request, automate, serve) resolve the wallet
    password from the env var named by ``password_env`` when present; TWAK then
    falls back to its own resolution order (flag > env > OS keychain).

    The demo defaults to non-signing paths: ``execute_swap`` is ``dry_run=True``
    by default and returns the command without running it.
    """

    command: str = "twak"

    # -- helpers --------------------------------------------------------------

    def _require(self) -> None:
        if not self.available():
            raise RuntimeError(_INSTALL_HINT)

    def _run(self, cmd: list[str], *, env: dict[str, str] | None = None) -> str:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
        return result.stdout.strip()

    @staticmethod
    def _password_args(password_env: str) -> list[str]:
        password = os.environ.get(password_env)
        return ["--password", password] if password else []

    def available(self) -> bool:
        return shutil.which(self.command) is not None

    # -- read-only ops --------------------------------------------------------

    def quote_swap(
        self,
        amount: float,
        from_asset: str,
        to_asset: str,
        *,
        chain: str = "bsc",
        usd: bool = False,
    ) -> str:
        self._require()
        src, dst = resolve_bsc_asset(from_asset), resolve_bsc_asset(to_asset)
        amt = ["--usd", str(amount)] if usd else [str(amount)]
        cmd = [self.command, "swap", *amt, src, dst, "--quote-only", "--chain", chain]
        return self._run(cmd)

    def wallet_portfolio(self) -> str:
        self._require()
        return self._run([self.command, "wallet", "portfolio"])

    def bsc_address(self) -> str:
        self._require()
        out = self._run([self.command, "wallet", "address", "--chain", "bsc", "--json"])
        return json.loads(out).get("address", "")

    def holding_usd(self, token_addr: str, wallet: str) -> float:
        """USD value of one ERC-20 holding on BSC, queried by contract (so it does
        NOT depend on TWAK's token auto-discovery, which misses freshly-bought names).
        Returns 0.0 if absent or unreadable."""
        try:
            out = self._run([
                self.command, "balance", "--chain", "bsc",
                "--address", wallet, "--token", token_addr, "--json",
            ])
            return float(json.loads(out).get("totalUsd", 0.0) or 0.0)
        except (subprocess.CalledProcessError, ValueError, KeyError):
            return 0.0

    def holdings_usd_bsc(self, symbol_to_addr: dict[str, str], wallet: str) -> dict[str, float]:
        """Per-symbol USD holdings on BSC for the given symbol->contract map."""
        out: dict[str, float] = {}
        for sym, addr in symbol_to_addr.items():
            v = self.holding_usd(addr, wallet)
            if v > 0.0:
                out[sym] = v
        return out

    def balance(self) -> str:
        self._require()
        return self._run([self.command, "balance"])

    def x402_quote(self, url: str) -> str:
        self._require()
        return self._run([self.command, "x402", "quote", url, "--json"])

    # -- signing ops ----------------------------------------------------------

    def execute_swap(
        self,
        amount: float,
        from_asset: str,
        to_asset: str,
        *,
        chain: str = "bsc",
        slippage_pct: float = 1.0,
        password_env: str = "TWAK_WALLET_PASSWORD",
        dry_run: bool = True,
        usd: bool = True,
    ) -> list[str] | str:
        """Build (and, unless ``dry_run``, run) a real swap.

        ``amount`` is a **USD value** by default (``usd=True``) — the agent sizes
        the book in USD — passed via TWAK's ``--usd`` flag; set ``usd=False`` to
        treat it as a source-token amount. Symbols are resolved to BSC contract
        addresses (TWAK rejects long-tail BEP-20 symbols). When executing, the
        command omits ``--quote-only`` and resolves the wallet password from
        ``password_env`` if set. Returns the command list on ``dry_run``, else stdout.
        """
        src, dst = resolve_bsc_asset(from_asset), resolve_bsc_asset(to_asset)
        amt = ["--usd", str(amount)] if usd else [str(amount)]
        cmd = [
            self.command,
            "swap",
            *amt,
            src,
            dst,
            "--chain",
            chain,
            "--slippage",
            str(slippage_pct),
            "--json",
        ]
        cmd += self._password_args(password_env)
        if dry_run:
            return cmd
        self._require()
        return self._run(cmd)

    def x402_request(
        self,
        url: str,
        *,
        max_payment: int | None = None,
        prefer_network: str = "bsc",
        auto_approve: bool = False,
        dry_run: bool = True,
    ) -> list[str] | str:
        """Pay-per-request fetch via x402. Signing op when actually run."""
        cmd = [self.command, "x402", "request", url, "--prefer-network", prefer_network, "--json"]
        if max_payment is not None:
            cmd += ["--max-payment", str(max_payment)]
        if auto_approve:
            cmd += ["--yes", "--auto-approve"]
        if dry_run:
            return cmd
        self._require()
        return self._run(cmd)

    def automate_dca(
        self,
        amount: float,
        from_asset: str,
        to_asset: str,
        interval: str,
        *,
        chain: str = "bsc",
        password_env: str = "TWAK_WALLET_PASSWORD",
        dry_run: bool = True,
    ) -> list[str] | str:
        """Schedule a recurring (DCA) swap. Guarantees >=1 trade/day if interval <= 1d."""
        cmd = [
            self.command,
            "automate",
            "add",
            str(amount),
            from_asset.upper(),
            to_asset.upper(),
            "--interval",
            interval,
            "--chain",
            chain,
        ]
        cmd += self._password_args(password_env)
        if dry_run:
            return cmd
        self._require()
        return self._run(cmd)

    def automate_limit(
        self,
        amount: float,
        from_asset: str,
        to_asset: str,
        price: float,
        condition: str,
        *,
        chain: str = "bsc",
        password_env: str = "TWAK_WALLET_PASSWORD",
        dry_run: bool = True,
    ) -> list[str] | str:
        """Schedule a limit swap triggered when price is above/below ``price``."""
        if condition not in ("above", "below"):
            raise ValueError("condition must be 'above' or 'below'")
        cmd = [
            self.command,
            "automate",
            "add",
            str(amount),
            from_asset.upper(),
            to_asset.upper(),
            "--price",
            str(price),
            "--condition",
            condition,
            "--chain",
            chain,
        ]
        cmd += self._password_args(password_env)
        if dry_run:
            return cmd
        self._require()
        return self._run(cmd)

    def serve_command(self, watch: bool = True, rest: bool = False, x402: bool = False) -> list[str]:
        """Build the argv for the long-running unattended agent server."""
        cmd = [self.command, "serve"]
        if watch:
            cmd.append("--watch")
        if rest:
            cmd.append("--rest")
        if x402:
            cmd.append("--x402")
        return cmd


@dataclass(frozen=True)
class RiskCaps:
    """Safety caps enforced before any signing swap.

    ``hard_drawdown_stop`` sits inside the contest's 30% disqualification line.
    ``max_position_frac`` is the execution backstop and must sit just ABOVE the
    strategy's own per-name cap (``StrategyConfig.max_weight`` = 0.34) — otherwise
    the gate silently reshapes the validated book and breaks decision parity.
    """

    max_position_frac: float = 0.35
    per_trade_max_loss_frac: float = 0.05
    daily_loss_limit_frac: float = 0.10
    hard_drawdown_stop: float = 0.22
    max_slippage_pct: float = 1.0
    min_trades_per_day: int = 1


def check_trade_allowed(
    caps: RiskCaps,
    *,
    current_drawdown: float,
    daily_loss: float,
    proposed_position_frac: float,
    slippage_pct: float,
) -> tuple[bool, str]:
    """Pure safety gate. Returns ``(allowed, reason)``.

    All fractions are non-negative magnitudes (e.g. a 25% drawdown is 0.25).
    The first failing check wins; on success the reason is ``"ok"``.
    """
    if current_drawdown >= caps.hard_drawdown_stop:
        return False, (
            f"hard drawdown stop hit: {current_drawdown:.2%} >= {caps.hard_drawdown_stop:.2%}"
        )
    if daily_loss >= caps.daily_loss_limit_frac:
        return False, (
            f"daily loss limit hit: {daily_loss:.2%} >= {caps.daily_loss_limit_frac:.2%}"
        )
    if proposed_position_frac > caps.max_position_frac:
        return False, (
            f"position too large: {proposed_position_frac:.2%} > {caps.max_position_frac:.2%}"
        )
    if slippage_pct > caps.max_slippage_pct:
        return False, (
            f"slippage too high: {slippage_pct:.2f}% > {caps.max_slippage_pct:.2f}%"
        )
    return True, "ok"
