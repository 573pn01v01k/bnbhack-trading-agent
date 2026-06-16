"""Pure-logic tests for signal panels. Synthetic hourly UTC data only."""
import numpy as np
import pandas as pd
import pytest

from bnbhack_agent.signals import (
    combine,
    flow_signal,
    market_regime,
    momentum,
    vol_adjusted_momentum,
    xs_zscore,
)


def _index(n, start="2026-01-01"):
    return pd.date_range(start, periods=n, freq="1h", tz="UTC")


# --------------------------------------------------------------------------
# xs_zscore
# --------------------------------------------------------------------------
def test_xs_zscore_rows_zero_mean_unit_std():
    idx = _index(4)
    panel = pd.DataFrame(
        {"A": [1.0, 2, 3, 4], "B": [2.0, 4, 6, 8], "C": [3.0, 6, 9, 12], "D": [4.0, 8, 12, 16]},
        index=idx,
    )
    z = xs_zscore(panel)
    # each row (>1 valid value) has ~0 cross-sectional mean
    assert np.allclose(z.mean(axis=1).values, 0.0, atol=1e-12)
    # pandas std is sample (ddof=1); re-standardizing the z-row by its own
    # sample std should give ~unit std.
    assert np.allclose(z.std(axis=1).values, 1.0, atol=1e-9)


def test_xs_zscore_constant_row_is_nan_not_inf():
    idx = _index(2)
    panel = pd.DataFrame({"A": [5.0, 1.0], "B": [5.0, 2.0]}, index=idx)
    z = xs_zscore(panel)
    # row 0 is constant -> std 0 -> replaced with NaN -> result all NaN (no inf)
    assert z.iloc[0].isna().all()
    assert not np.isinf(z.values[~np.isnan(z.values)]).any()


# --------------------------------------------------------------------------
# momentum
# --------------------------------------------------------------------------
def test_momentum_equals_pct_change_lookback():
    idx = _index(20)
    price = pd.DataFrame(
        {"A": np.linspace(100, 200, 20), "B": np.linspace(50, 10, 20)}, index=idx
    )
    for k in (1, 3, 5):
        pd.testing.assert_frame_equal(momentum(price, lookback=k), price.pct_change(k))


def test_vol_adjusted_momentum_shape_and_no_inf():
    idx = _index(120)
    rng = np.random.default_rng(0)
    price = pd.DataFrame(
        {s: 100 * np.cumprod(1 + rng.normal(0, 0.01, 120)) for s in ("A", "B", "C")},
        index=idx,
    )
    vam = vol_adjusted_momentum(price, lookback=48, vol_window=72)
    assert vam.shape == price.shape
    assert not np.isinf(vam.values[~np.isnan(vam.values)]).any()


# --------------------------------------------------------------------------
# flow_signal
# --------------------------------------------------------------------------
def test_flow_signal_smooths_and_preserves_shape():
    idx = _index(6)
    flow = pd.DataFrame({"A": [1.0, -1, 1, -1, 1, -1], "B": [0.0, 0, 0, 0, 0, 0]}, index=idx)
    out = flow_signal(flow, smooth=2)
    assert out.shape == flow.shape
    # rolling mean(2): bar1 of A = mean(1,-1) = 0
    assert out.iloc[1]["A"] == pytest.approx(0.0, abs=1e-12)


# --------------------------------------------------------------------------
# combine
# --------------------------------------------------------------------------
def test_combine_shape_matches_price():
    idx = _index(160)
    rng = np.random.default_rng(1)
    price = pd.DataFrame(
        {s: 100 * np.cumprod(1 + rng.normal(0, 0.01, 160)) for s in ("A", "B", "C", "D")},
        index=idx,
    )
    score = combine(price, mom_lookback=48, vol_window=72)
    assert score.shape == price.shape
    assert list(score.columns) == list(price.columns)
    assert score.index.equals(price.index)


def test_combine_ignores_flow_when_w_flow_zero():
    idx = _index(160)
    rng = np.random.default_rng(2)
    price = pd.DataFrame(
        {s: 100 * np.cumprod(1 + rng.normal(0, 0.01, 160)) for s in ("A", "B", "C")},
        index=idx,
    )
    flow = pd.DataFrame(
        {s: rng.normal(0, 1, 160) for s in ("A", "B", "C")}, index=idx
    )
    base = combine(price, mom_lookback=48, vol_window=72, w_flow=0.0)
    with_flow_but_zero_weight = combine(
        price, mom_lookback=48, vol_window=72, flow_imbalance=flow, w_flow=0.0
    )
    pd.testing.assert_frame_equal(base, with_flow_but_zero_weight)


def test_combine_flow_changes_score_when_w_flow_nonzero():
    idx = _index(160)
    rng = np.random.default_rng(3)
    price = pd.DataFrame(
        {s: 100 * np.cumprod(1 + rng.normal(0, 0.01, 160)) for s in ("A", "B", "C")},
        index=idx,
    )
    flow = pd.DataFrame(
        {s: rng.normal(0, 1, 160) for s in ("A", "B", "C")}, index=idx
    )
    base = combine(price, w_flow=0.0)
    mixed = combine(price, flow_imbalance=flow, w_momentum=1.0, w_flow=1.0)
    # the two score panels must differ once flow is mixed in
    diff = (base.fillna(0) - mixed.fillna(0)).abs().sum().sum()
    assert diff > 0


# --------------------------------------------------------------------------
# market_regime
# --------------------------------------------------------------------------
def test_market_regime_returns_bool_series():
    idx = _index(120)
    price = pd.DataFrame({"BTC": np.linspace(100, 200, 120)}, index=idx)
    reg = market_regime(price, ref="BTC", ma=24)
    assert isinstance(reg, pd.Series)
    assert reg.dtype == bool
    assert reg.index.equals(price.index)


def test_market_regime_true_when_ref_below_ma():
    # down-then-up: first half falls (price below trailing MA -> risk-off True),
    # later it rises above the MA -> risk-on False.
    n = 120
    idx = _index(n)
    down = np.linspace(200, 100, n // 2)
    up = np.linspace(100, 300, n - n // 2)
    btc = np.concatenate([down, up])
    price = pd.DataFrame({"BTC": btc}, index=idx)
    reg = market_regime(price, ref="BTC", ma=10)
    # somewhere in the falling leg (after the MA warms up) we are below the MA
    assert reg.iloc[20:55].any()
    # by the end of the rally we are above the MA -> risk-on
    assert not reg.iloc[-1]


def test_market_regime_missing_ref_all_false():
    idx = _index(10)
    price = pd.DataFrame({"ETH": np.arange(10.0)}, index=idx)
    reg = market_regime(price, ref="BTC", ma=5)
    assert (~reg).all()
    assert len(reg) == len(price)
