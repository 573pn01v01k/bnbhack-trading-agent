from __future__ import annotations

from dataclasses import replace

from .indicators import ema, macd, rsi, sma
from .models import Candle, StrategySpec

CMC_CAPS = ["CoinMarketCap Data API / MCP for OHLCV, technicals, sentiment, derivatives and narratives"]
TWAK_CAPS = ["Trust Wallet Agent Kit quote-only / execution adapter for Track 1 upgrade"]
BNB_CAPS = ["BNB Chain venue policy: BSC/PancakeSwap/BSC perps compatible signals"]


def initial_candidates() -> list[StrategySpec]:
    return [
        StrategySpec(
            name="regime_adaptive_momentum",
            description="Trend-following BNB/BSC strategy gated by RSI and MACD regime; CMC data is primary signal source.",
            parameters={"fast": 8, "slow": 21, "rsi_min": 42, "rsi_max": 76, "macd_required": True},
            entry_rules=["close > fast EMA > slow SMA", "RSI is between rsi_min and rsi_max", "MACD histogram is positive when macd_required=true"],
            exit_rules=["close < fast EMA", "RSI > 82", "MACD histogram turns negative for two bars"],
            risk_policy={"max_drawdown": 0.25, "target_exposure": 0.55, "fee_bps": 8, "max_position": 1.0},
            sponsor_capabilities=CMC_CAPS + TWAK_CAPS + BNB_CAPS,
            tags=["track2", "track1-upgrade", "momentum", "risk-adjusted"],
            monolit_enrichment="Optional wallet-flow anomaly can veto entries when smart money exits BNB Chain liquidity.",
        ),
        StrategySpec(
            name="pullback_rebound",
            description="Mean-reversion skill that buys deep pullbacks only when the higher-timeframe trend remains intact.",
            parameters={"fast": 10, "slow": 30, "rsi_buy": 38, "rsi_exit": 58},
            entry_rules=["close > slow SMA", "RSI < rsi_buy", "previous 3-bar return is negative"],
            exit_rules=["RSI > rsi_exit", "close < slow SMA"],
            risk_policy={"max_drawdown": 0.20, "target_exposure": 0.35, "fee_bps": 8, "max_position": 1.0},
            sponsor_capabilities=CMC_CAPS + TWAK_CAPS + BNB_CAPS,
            tags=["track2", "mean-reversion", "risk-filter"],
            monolit_enrichment="Optional Monolit MCP whale-flow anomaly can increase confidence on capitulation rebounds.",
        ),
        StrategySpec(
            name="volatility_breakout",
            description="Breakout skill that enters when BNB closes above recent range with expanding volume.",
            parameters={"lookback": 18, "volume_window": 12, "rsi_max": 80},
            entry_rules=["close breaks above lookback high", "volume > volume SMA", "RSI < rsi_max"],
            exit_rules=["close loses midpoint of breakout range", "RSI > 84"],
            risk_policy={"max_drawdown": 0.28, "target_exposure": 0.45, "fee_bps": 8, "max_position": 1.0},
            sponsor_capabilities=CMC_CAPS + TWAK_CAPS + BNB_CAPS,
            tags=["track2", "breakout", "volume"],
            monolit_enrichment="Optional liquidity-pool depth anomaly can reject thin breakouts.",
        ),
        StrategySpec(
            name="adaptive_trend_perps",
            description="Long/short BNB perps strategy that follows higher-timeframe trend and can profit during drawdown windows.",
            parameters={
                "fast": 34,
                "slow": 144,
                "rsi_long_min": 30,
                "rsi_long_max": 65,
                "rsi_short_min": 40,
                "short_take_profit_rsi": 18,
            },
            entry_rules=[
                "Long when close > fast EMA > slow SMA, MACD histogram is positive, and RSI is within long bounds",
                "Short when close < fast EMA < slow SMA, MACD histogram is negative, and RSI is above rsi_short_min",
                "Use previous closed candle only; never trade on current candle information",
            ],
            exit_rules=[
                "Exit long when close loses fast EMA or RSI overheats above 86",
                "Exit short when close recovers fast EMA or RSI reaches short_take_profit_rsi",
                "Optional Monolit wallet-flow veto exits risk-on positions when smart-flow anomaly is strongly negative",
            ],
            risk_policy={"max_drawdown": 0.22, "target_exposure": 0.25, "fee_bps": 8, "max_position": 1.0, "allow_short": True},
            sponsor_capabilities=CMC_CAPS + TWAK_CAPS + BNB_CAPS,
            tags=["track2", "track1-upgrade", "perps", "long-short", "drawdown-alpha"],
            monolit_enrichment="Optional Monolit MCP smart-flow anomaly can veto longs or increase confidence in shorts during liquidity exits.",
        ),
    ]


def generate_signals(strategy: StrategySpec, candles: list[Candle], features: dict[str, list[float]] | None = None) -> list[int]:
    if strategy.name.startswith("regime_adaptive_momentum"):
        return _regime_adaptive_momentum(strategy, candles, features or {})
    if strategy.name.startswith("pullback_rebound"):
        return _pullback_rebound(strategy, candles, features or {})
    if strategy.name.startswith("volatility_breakout"):
        return _volatility_breakout(strategy, candles, features or {})
    if strategy.name.startswith("adaptive_trend_perps"):
        return _adaptive_trend_perps(strategy, candles, features or {})
    raise ValueError(f"unknown strategy: {strategy.name}")


def _monolit_veto(i: int, features: dict[str, list[float]]) -> bool:
    values = features.get("wallet_flow_anomaly") or features.get("smart_flow")
    return bool(values and i < len(values) and values[i] < -0.8)


def _regime_adaptive_momentum(strategy: StrategySpec, candles: list[Candle], features: dict[str, list[float]]) -> list[int]:
    closes = [c.close for c in candles]
    fast = int(strategy.parameters["fast"])
    slow = int(strategy.parameters["slow"])
    fast_ema = ema(closes, fast)
    slow_sma = sma(closes, slow)
    rsi_values = rsi(closes, 14)
    _, _, hist = macd(closes, fast=max(3, fast // 2), slow=max(fast + 1, slow), signal_period=5)
    out = [0] * len(candles)
    for i in range(1, len(candles)):
        if any(x is None for x in (fast_ema[i - 1], slow_sma[i - 1], rsi_values[i - 1], hist[i - 1])):
            out[i] = 0
            continue
        assert fast_ema[i - 1] is not None and slow_sma[i - 1] is not None and rsi_values[i - 1] is not None
        rsi_ok = float(strategy.parameters["rsi_min"]) <= rsi_values[i - 1] <= float(strategy.parameters["rsi_max"])
        macd_ok = (hist[i - 1] or 0) > 0 if strategy.parameters.get("macd_required", True) else True
        trend_ok = closes[i - 1] > fast_ema[i - 1] > slow_sma[i - 1]
        exit_now = closes[i - 1] < fast_ema[i - 1] or rsi_values[i - 1] > 82 or _monolit_veto(i - 1, features)
        if out[i - 1] and not exit_now:
            out[i] = 1
        elif trend_ok and rsi_ok and macd_ok and not _monolit_veto(i - 1, features):
            out[i] = 1
        else:
            out[i] = 0
    return out


def _pullback_rebound(strategy: StrategySpec, candles: list[Candle], features: dict[str, list[float]]) -> list[int]:
    closes = [c.close for c in candles]
    slow_sma = sma(closes, int(strategy.parameters["slow"]))
    rsi_values = rsi(closes, 14)
    out = [0] * len(candles)
    for i in range(3, len(candles)):
        if slow_sma[i - 1] is None or rsi_values[i - 1] is None:
            continue
        prev_three_return = closes[i - 1] / closes[i - 4] - 1
        trend_intact = closes[i - 1] > slow_sma[i - 1]
        buy = trend_intact and rsi_values[i - 1] < float(strategy.parameters["rsi_buy"]) and prev_three_return < -0.01
        hold = bool(out[i - 1]) and rsi_values[i - 1] < float(strategy.parameters["rsi_exit"]) and trend_intact
        out[i] = 1 if (buy or hold) and not _monolit_veto(i - 1, features) else 0
    return out


def _volatility_breakout(strategy: StrategySpec, candles: list[Candle], features: dict[str, list[float]]) -> list[int]:
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    lookback = int(strategy.parameters["lookback"])
    volume_sma = sma(volumes, int(strategy.parameters["volume_window"]))
    rsi_values = rsi(closes, 14)
    out = [0] * len(candles)
    for i in range(lookback + 1, len(candles)):
        if volume_sma[i - 1] is None or rsi_values[i - 1] is None:
            continue
        recent_high = max(closes[i - lookback - 1 : i - 1])
        recent_low = min(closes[i - lookback - 1 : i - 1])
        midpoint = (recent_high + recent_low) / 2
        buy = closes[i - 1] > recent_high and volumes[i - 1] > volume_sma[i - 1] and rsi_values[i - 1] < float(strategy.parameters["rsi_max"])
        hold = bool(out[i - 1]) and closes[i - 1] > midpoint and rsi_values[i - 1] < 84
        out[i] = 1 if (buy or hold) and not _monolit_veto(i - 1, features) else 0
    return out


def _adaptive_trend_perps(strategy: StrategySpec, candles: list[Candle], features: dict[str, list[float]]) -> list[int]:
    """Long/short trend follower for BSC perps-compatible Track 1 upgrade."""
    closes = [c.close for c in candles]
    fast = int(strategy.parameters["fast"])
    slow = int(strategy.parameters["slow"])
    fast_ema = ema(closes, fast)
    slow_sma = sma(closes, slow)
    rsi_values = rsi(closes, 14)
    _, _, hist = macd(closes, fast=max(3, fast // 2), slow=max(fast + 1, slow), signal_period=5)
    out = [0] * len(candles)
    for i in range(1, len(candles)):
        if any(x is None for x in (fast_ema[i - 1], slow_sma[i - 1], rsi_values[i - 1], hist[i - 1])):
            continue
        assert fast_ema[i - 1] is not None and slow_sma[i - 1] is not None and rsi_values[i - 1] is not None and hist[i - 1] is not None
        price = closes[i - 1]
        rsi_value = rsi_values[i - 1]
        macd_hist = hist[i - 1]
        long_entry = (
            price > fast_ema[i - 1] > slow_sma[i - 1]
            and float(strategy.parameters["rsi_long_min"]) <= rsi_value <= float(strategy.parameters["rsi_long_max"])
            and macd_hist > 0
            and not _monolit_veto(i - 1, features)
        )
        strong_breakdown = price < fast_ema[i - 1] and price < slow_sma[i - 1] and price / slow_sma[i - 1] < 0.98
        short_entry = (
            price < fast_ema[i - 1]
            and price < slow_sma[i - 1]
            and macd_hist < 0
            and (float(strategy.parameters["rsi_short_min"]) <= rsi_value <= 70 or strong_breakdown)
        )
        short_take_profit = rsi_value < float(strategy.parameters["short_take_profit_rsi"]) and closes[i - 1] > closes[i - 2]
        if out[i - 1] == 1:
            out[i] = 0 if price < fast_ema[i - 1] or rsi_value > 86 or _monolit_veto(i - 1, features) else 1
        elif out[i - 1] == -1:
            out[i] = 0 if price > fast_ema[i - 1] or short_take_profit else -1
        elif long_entry:
            out[i] = 1
        elif short_entry:
            out[i] = -1
    return out


def mutate_strategy(strategy: StrategySpec, critique: str, iteration: int) -> StrategySpec:
    params = dict(strategy.parameters)
    risk = dict(strategy.risk_policy)
    lower = critique.lower()
    if "drawdown" in lower:
        risk["max_drawdown"] = max(0.12, float(risk.get("max_drawdown", 0.25)) - 0.03)
        if "rsi_max" in params:
            params["rsi_max"] = max(62, float(params["rsi_max"]) - 4)
        if "rsi_long_max" in params:
            params["rsi_long_max"] = max(55, float(params["rsi_long_max"]) - 4)
        if "slow" in params:
            params["slow"] = int(float(params["slow"]) + 4)
    elif "too little exposure" in lower:
        if "rsi_min" in params:
            params["rsi_min"] = max(30, float(params["rsi_min"]) - 4)
        if "rsi_buy" in params:
            params["rsi_buy"] = min(50, float(params["rsi_buy"]) + 4)
        if "rsi_short_min" in params:
            params["rsi_short_min"] = max(25, float(params["rsi_short_min"]) - 5)
        if "lookback" in params:
            params["lookback"] = max(8, int(float(params["lookback"]) - 3))
    elif "turnover" in lower:
        if "fast" in params:
            params["fast"] = int(float(params["fast"]) + 2)
        if "lookback" in params:
            params["lookback"] = int(float(params["lookback"]) + 3)
    else:
        if "fast" in params and "slow" in params:
            params["fast"] = max(3, int(float(params["fast"]) - 1))
            params["slow"] = int(float(params["slow"]) + 2)
        elif "lookback" in params:
            params["lookback"] = max(8, int(float(params["lookback"]) - 2))
    return replace(strategy, name=f"{strategy.name}_iter{iteration}", parameters=params, risk_policy=risk)
