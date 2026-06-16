from __future__ import annotations

import math
from statistics import fmean
from typing import Optional, Union

Number = Union[float, int]
MaybeFloat = Optional[float]


def _validate_window(window: int) -> None:
    if window <= 0:
        raise ValueError("window must be positive")


def sma(values: list[Number], window: int) -> list[MaybeFloat]:
    """Simple moving average with None until enough observations exist."""
    _validate_window(window)
    out: list[MaybeFloat] = []
    running = 0.0
    for i, value in enumerate(values):
        running += float(value)
        if i >= window:
            running -= float(values[i - window])
        out.append(None if i + 1 < window else running / window)
    return out


def ema(values: list[Number], window: int) -> list[MaybeFloat]:
    """Exponential moving average seeded by the first value."""
    _validate_window(window)
    if not values:
        return []
    alpha = 2 / (window + 1)
    prev = float(values[0])
    out: list[MaybeFloat] = [prev]
    for value in values[1:]:
        prev = alpha * float(value) + (1 - alpha) * prev
        out.append(prev)
    return out


def rsi(values: list[Number], window: int = 14) -> list[MaybeFloat]:
    """Wilder-style RSI; returns None until the initial window is available."""
    _validate_window(window)
    if not values:
        return []
    gains = [0.0]
    losses = [0.0]
    for prev, cur in zip(values, values[1:]):
        delta = float(cur) - float(prev)
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))
    out: list[MaybeFloat] = []
    avg_gain = avg_loss = None
    for i in range(len(values)):
        if i < window:
            out.append(None)
            continue
        if i == window:
            avg_gain = fmean(gains[1 : window + 1])
            avg_loss = fmean(losses[1 : window + 1])
        else:
            assert avg_gain is not None and avg_loss is not None
            avg_gain = (avg_gain * (window - 1) + gains[i]) / window
            avg_loss = (avg_loss * (window - 1) + losses[i]) / window
        if avg_loss == 0:
            out.append(100.0)
        else:
            rs = avg_gain / avg_loss
            out.append(100 - (100 / (1 + rs)))
    return out


def macd(values: list[Number], fast: int = 12, slow: int = 26, signal_period: int = 9) -> tuple[list[MaybeFloat], list[MaybeFloat], list[MaybeFloat]]:
    """MACD line, signal line, histogram."""
    if fast >= slow:
        raise ValueError("fast window must be smaller than slow window")
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    line: list[MaybeFloat] = []
    for f, s in zip(fast_ema, slow_ema):
        line.append(None if f is None or s is None else f - s)
    clean_line = [0.0 if item is None else item for item in line]
    signal = ema(clean_line, signal_period)
    hist: list[MaybeFloat] = []
    for macd_value, signal_value in zip(line, signal):
        hist.append(None if macd_value is None or signal_value is None else macd_value - signal_value)
    return line, signal, hist


def rolling_std(values: list[Number], window: int) -> list[MaybeFloat]:
    _validate_window(window)
    out: list[MaybeFloat] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
            continue
        chunk = [float(v) for v in values[i - window + 1 : i + 1]]
        mean = fmean(chunk)
        out.append(math.sqrt(fmean([(x - mean) ** 2 for x in chunk])))
    return out
