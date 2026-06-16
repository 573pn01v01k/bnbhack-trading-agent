"""Walk-forward engine tests on a small synthetic panel. No network."""
import math

import numpy as np
import pandas as pd
import pytest

from bnbhack_agent.portfolio import PortfolioResult
from bnbhack_agent.walkforward import WalkForwardReport, default_grid, walk_forward

TRAIN_H, TEST_H = 480, 120
N_BARS = 900

# A small grid keeps the full-panel walk-forward runs fast while still
# exercising selection (varied lookbacks/top_k/regime). default_grid() itself
# is checked separately for membership below.
SMALL_GRID = [
    {"mom_lookback": 24, "vol_window": 48, "top_k": 3, "max_weight": 0.34, "regime": False},
    {"mom_lookback": 48, "vol_window": 72, "top_k": 5, "max_weight": 0.5, "regime": True},
]


def _index(n, start="2026-01-01"):
    return pd.date_range(start, periods=n, freq="1h", tz="UTC")


def _synthetic_panel(n=N_BARS, n_assets=6, seed=0):
    """6 assets: one (BTC) persistently trends up, the rest are noisy/flat."""
    idx = _index(n)
    rng = np.random.default_rng(seed)
    cols = {}
    # persistently trending asset
    drift = np.full(n, 0.0004)
    cols["BTC"] = 100 * np.cumprod(1 + drift + rng.normal(0, 0.003, n))
    # other noisy assets with varied small drifts
    names = ["ETH", "BNB", "SOL", "ADA", "XRP"][: n_assets - 1]
    for name in names:
        d = rng.normal(0, 0.0002)
        cols[name] = 100 * np.cumprod(1 + d + rng.normal(0, 0.006, n))
    return pd.DataFrame(cols, index=idx)


@pytest.fixture(scope="module")
def report():
    """Run the (small-grid) walk-forward once and share across tests."""
    price = _synthetic_panel()
    return walk_forward(
        price, grid=SMALL_GRID, train_h=TRAIN_H, test_h=TEST_H, baseline_symbol="BTC"
    )


def test_walk_forward_runs_and_reports(report):
    assert isinstance(report, WalkForwardReport)
    assert isinstance(report.oos, PortfolioResult)
    assert isinstance(report.baselines, dict)
    assert len(report.folds) >= 1

    # fold count = floor((n - train_h - test_h)/test_h) + 1
    expected_folds = math.floor((N_BARS - TRAIN_H - TEST_H) / TEST_H) + 1
    assert len(report.folds) == expected_folds


def test_walk_forward_selected_params_from_grid(report):
    assert report.param_grid_size == len(SMALL_GRID)
    # every selected param dict must be a member of the grid
    for fold in report.folds:
        assert fold.params in SMALL_GRID


def test_walk_forward_summary_shape(report):
    summ = report.summary()
    assert summ["n_folds"] == len(report.folds)
    assert summ["param_grid_size"] == report.param_grid_size
    assert "oos" in summ and "baselines" in summ
    assert isinstance(summ["selected_params"], list)
    assert len(summ["selected_params"]) == len(report.folds)


def test_walk_forward_baselines_present(report):
    # OOS span is non-empty -> baselines populated
    assert "equal_weight" in report.baselines
    assert "BTC_hold" in report.baselines
    for v in report.baselines.values():
        assert isinstance(v, PortfolioResult)


def test_walk_forward_default_grid_membership():
    """Selected params with the real default_grid() are members of it.

    Uses a shorter panel so a single fold runs cheaply over the full grid.
    """
    price = _synthetic_panel(n=720)
    grid = default_grid()
    rep = walk_forward(price, grid=grid, train_h=480, test_h=120)
    assert rep.param_grid_size == len(grid)
    assert len(rep.folds) >= 1
    for fold in rep.folds:
        assert fold.params in grid


def test_walk_forward_single_param_grid(report):
    price = _synthetic_panel()
    # a trivial 1-element grid still produces a valid report
    grid = [{"mom_lookback": 48, "vol_window": 72, "top_k": 3, "max_weight": 0.34, "regime": False}]
    rep = walk_forward(price, grid=grid, train_h=TRAIN_H, test_h=TEST_H)
    assert rep.param_grid_size == 1
    assert all(f.params in grid for f in rep.folds)
    assert rep.oos.n_bars > 0
