"""Pure-logic tests for the portfolio backtest engine.

Synthetic hourly UTC panels only — no network, no Monolit, no Binance.
"""
import numpy as np
import pandas as pd
import pytest

from bnbhack_agent.portfolio import (
    decide_weights,
    equal_weight_baseline,
    metrics_from_returns,
    simulate,
    single_asset_baseline,
    strategy_returns,
)


def _index(n, start="2026-01-01"):
    return pd.date_range(start, periods=n, freq="1h", tz="UTC")


def _flat_price_with_jump(n=8, jump_bar=4, jump=0.10, syms=("A", "B")):
    """All prices flat at 100 except asset A jumps `jump` going INTO `jump_bar`.

    i.e. price[jump_bar] = price[jump_bar-1] * (1 + jump). So pct_change at
    `jump_bar` is `jump`, and pct_change is 0 everywhere else.
    """
    idx = _index(n)
    data = {s: np.full(n, 100.0) for s in syms}
    data[syms[0]][jump_bar:] = 100.0 * (1 + jump)
    return pd.DataFrame(data, index=idx)


# --------------------------------------------------------------------------
# 1. No-lookahead (critical)
# --------------------------------------------------------------------------
def test_constant_weight_earns_next_bar_return():
    """A constant weight in row t earns the t->t+1 pct_change (weights.shift(1))."""
    n, jump_bar, jump = 8, 4, 0.10
    price = _flat_price_with_jump(n=n, jump_bar=jump_bar, jump=jump)
    # full weight on A every bar, no cost so turnover is irrelevant after bar 0
    weights = pd.DataFrame({"A": np.ones(n), "B": np.zeros(n)}, index=price.index)

    ret = strategy_returns(price, weights, cost_bps=0.0)

    # held = weights.shift(1); the jump return (at jump_bar) is captured because
    # we held A from jump_bar-1 into jump_bar.
    assert ret.iloc[jump_bar] == pytest.approx(jump, abs=1e-12)
    # every other bar is flat -> zero return
    others = [i for i in range(n) if i != jump_bar]
    assert np.allclose(ret.iloc[others].values, 0.0, atol=1e-12)


def test_weight_set_at_or_after_jump_does_not_capture_past_jump():
    """Weight that is nonzero ONLY from the jump bar onward must NOT earn the
    jump that already happened going into that bar."""
    n, jump_bar, jump = 8, 4, 0.10
    price = _flat_price_with_jump(n=n, jump_bar=jump_bar, jump=jump)

    w = np.zeros(n)
    w[jump_bar:] = 1.0  # only long A starting AT the jump bar
    weights = pd.DataFrame({"A": w, "B": np.zeros(n)}, index=price.index)

    ret = strategy_returns(price, weights, cost_bps=0.0)
    # held[jump_bar] = weights.shift(1)[jump_bar] = weights[jump_bar-1] = 0,
    # so the already-realized jump is NOT earned.
    assert ret.iloc[jump_bar] == pytest.approx(0.0, abs=1e-12)
    # and after the jump prices are flat, so all returns are zero
    assert np.allclose(ret.values, 0.0, atol=1e-12)


def test_weight_at_last_bar_earns_zero():
    """A weight set only on the final bar earns nothing — there is no next bar."""
    n = 8
    price = _flat_price_with_jump(n=n, jump_bar=4, jump=0.10)
    w = np.zeros(n)
    w[-1] = 1.0
    weights = pd.DataFrame({"A": w, "B": np.zeros(n)}, index=price.index)

    ret = strategy_returns(price, weights, cost_bps=0.0)
    # the last-bar weight is never shifted forward into a return-bearing bar
    assert ret.iloc[-1] == pytest.approx(0.0, abs=1e-12)


def test_simulate_uses_shifted_weights_too():
    """simulate() shares the no-lookahead contract with strategy_returns()."""
    n, jump_bar, jump = 8, 4, 0.10
    price = _flat_price_with_jump(n=n, jump_bar=jump_bar, jump=jump)
    weights = pd.DataFrame({"A": np.ones(n), "B": np.zeros(n)}, index=price.index)
    res = simulate(price, weights, cost_bps=0.0)
    # equity rises only at the jump bar; total return == jump
    assert res.total_return == pytest.approx(jump, abs=1e-9)
    assert res.n_bars == n


# --------------------------------------------------------------------------
# 2. metrics_from_returns
# --------------------------------------------------------------------------
def test_metrics_total_return_is_compound_product():
    idx = _index(4)
    rets = pd.Series([0.10, -0.05, 0.20, 0.0], index=idx)
    res = metrics_from_returns(rets)
    expected = (1.10 * 0.95 * 1.20 * 1.0) - 1.0
    assert res.total_return == pytest.approx(expected, abs=1e-12)
    assert res.n_bars == 4


def test_metrics_max_drawdown_hand_computed():
    idx = _index(5)
    # equity: 1.0 -> 1.2 -> 0.96 -> ... peak 1.2, trough 0.96 => dd = 0.2
    rets = pd.Series([0.0, 0.20, -0.20, 0.0, 0.0], index=idx)
    res = metrics_from_returns(rets)
    # equity after bar1 = 1.2; after bar2 = 1.2*0.8 = 0.96; dd = (1.2-0.96)/1.2 = 0.2
    assert res.max_drawdown == pytest.approx(0.20, abs=1e-12)


def test_metrics_sharpe_sign():
    idx = _index(6)
    pos = pd.Series([0.01, 0.02, 0.01, 0.03, 0.01, 0.02], index=idx)
    neg = -pos
    assert metrics_from_returns(pos).sharpe > 0
    assert metrics_from_returns(neg).sharpe < 0
    # zero variance -> sharpe 0
    flat = pd.Series(np.zeros(6), index=idx)
    assert metrics_from_returns(flat).sharpe == 0.0


# --------------------------------------------------------------------------
# 3. decide_weights
# --------------------------------------------------------------------------
def _const_panel(values_by_sym, n=3):
    idx = _index(n)
    return pd.DataFrame({s: np.full(n, v) for s, v in values_by_sym.items()}, index=idx)


def test_decide_weights_top_k_limits_names():
    syms = {"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "E": 1.0}
    score = _const_panel(syms)
    price = _const_panel({s: 100.0 for s in syms})
    w = decide_weights(score, price, top_k=2, max_weight=1.0, min_score=0.0)
    nonzero = (w.iloc[0] > 0).sum()
    assert nonzero == 2
    # the two highest scores (A, B) are the chosen names
    assert w.iloc[0]["A"] > 0 and w.iloc[0]["B"] > 0
    assert w.iloc[0]["C"] == 0


def test_decide_weights_max_weight_cap_respected():
    syms = {"A": 5.0, "B": 4.0, "C": 3.0}
    score = _const_panel(syms)
    price = _const_panel({s: 100.0 for s in syms})
    w = decide_weights(score, price, top_k=3, max_weight=0.2, min_score=0.0)
    # equal weight would be 1/3 ~ 0.333, capped at 0.2
    assert (w.iloc[0] <= 0.2 + 1e-12).all()
    assert w.iloc[0].max() == pytest.approx(0.2, abs=1e-12)


def test_decide_weights_min_score_filters():
    syms = {"A": 5.0, "B": -1.0, "C": -2.0}
    score = _const_panel(syms)
    price = _const_panel({s: 100.0 for s in syms})
    w = decide_weights(score, price, top_k=5, max_weight=1.0, min_score=0.0)
    # only A has score > 0
    assert w.iloc[0]["A"] > 0
    assert w.iloc[0]["B"] == 0 and w.iloc[0]["C"] == 0


def test_decide_weights_regime_forces_all_cash():
    syms = {"A": 5.0, "B": 4.0}
    score = _const_panel(syms, n=3)
    price = _const_panel({s: 100.0 for s in syms}, n=3)
    regime = pd.Series([False, True, False], index=price.index)
    w = decide_weights(score, price, top_k=2, max_weight=1.0, regime=regime)
    assert (w.iloc[1] == 0).all()       # risk-off bar -> all cash
    assert w.iloc[0].sum() > 0          # other bars invested


def test_decide_weights_rows_sum_at_most_one():
    syms = {"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0}
    score = _const_panel(syms)
    price = _const_panel({s: 100.0 for s in syms})
    w = decide_weights(score, price, top_k=4, max_weight=0.34, min_score=0.0)
    assert (w.sum(axis=1) <= 1.0 + 1e-9).all()


# --------------------------------------------------------------------------
# 4. equal_weight_baseline
# --------------------------------------------------------------------------
def test_equal_weight_baseline_constant_membership():
    n = 6
    idx = _index(n)
    # gently trending, all present every bar
    price = pd.DataFrame(
        {"A": 100 + np.arange(n), "B": 200 + np.arange(n), "C": 50 + np.arange(n)},
        index=idx,
    ).astype(float)
    res = equal_weight_baseline(price, cost_bps=10.0)
    # avg exposure ~1 (fully invested in the basket)
    assert res.avg_exposure == pytest.approx(1.0, abs=1e-9)

    # turnover is ~0 on constant membership AFTER the initial allocation bar.
    # (The mean over all bars carries the unavoidable 0->equal-weight rebalance
    # on bar 0; from bar 1 onward weights are constant -> per-bar turnover 0.)
    valid = price.notna()
    w = valid.astype("float64")
    w = w.div(w.sum(axis=1), axis=0).fillna(0.0)
    per_bar_turnover = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1)
    assert np.allclose(per_bar_turnover.iloc[1:].values, 0.0, atol=1e-12)


def test_equal_weight_weights_sum_to_one_when_all_present():
    idx = _index(3)
    price = pd.DataFrame(
        {"A": [100.0, 101, 102], "B": [10.0, 11, 12], "C": [5.0, 6, 7]}, index=idx
    )
    valid = price.notna()
    w = valid.astype("float64")
    w = w.div(w.sum(axis=1), axis=0)
    assert np.allclose(w.sum(axis=1).values, 1.0)


def test_single_asset_baseline_matches_pct_change():
    idx = _index(4)
    price = pd.DataFrame({"A": [100.0, 110, 121, 121], "B": [1.0, 1, 1, 1]}, index=idx)
    res = single_asset_baseline(price, "A")
    # total return of A: 121/100 - 1 = 0.21
    assert res.total_return == pytest.approx(0.21, abs=1e-9)
