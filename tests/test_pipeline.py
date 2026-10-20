"""Unit tests: no look-ahead, correct position lag, and the averaging effect on a random walk."""
import numpy as np
import pandas as pd

from trendoos.pipeline import Cfg, backtest, signal, stats

CFG = Cfg(raw=None, out=None, cost_bps=5, cost_bps_stress=25, sma_months=10, mom_months=12,
          shiller_end="2023-06-01", pub_date="2007-06-01", allocation_usd=1e9)


def _series(n=240, seed=0):
    rng = np.random.default_rng(seed)
    r = pd.Series(rng.normal(0.006, 0.045, n), index=pd.date_range("2000-01-01", periods=n, freq="MS"))
    return (1 + r).cumprod() * 100, r


def test_signal_has_no_lookahead():
    px, r = _series()
    s1 = signal(px, r, "SMA10", CFG)
    px2, r2 = px.copy(), r.copy()
    px2.iloc[150:] *= 3.0  # change the future only
    r2.iloc[150:] = 0.5
    s2 = signal(px2, r2, "SMA10", CFG)
    assert s1.iloc[:150].equals(s2.iloc[:150])


def test_position_is_lagged_one_month():
    px, r = _series()
    sig = signal(px, r, "TSMOM12", CFG)
    bt = backtest(r, pd.Series(0.0, index=r.index), sig, 0.0)
    assert bt.pos.equals(sig.shift(1).dropna().reindex(bt.index))


def test_costs_reduce_returns():
    px, r = _series()
    sig = signal(px, r, "SMA10", CFG)
    cash = pd.Series(0.0, index=r.index)
    assert backtest(r, cash, sig, 50).strat.sum() < backtest(r, cash, sig, 0).strat.sum()


def test_averaging_creates_autocorrelation():
    rng = np.random.default_rng(1)
    daily = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.01, 21 * 600))))
    month = np.arange(len(daily)) // 21
    avg = daily.groupby(month).mean().pct_change().dropna()
    end = daily.groupby(month).last().pct_change().dropna()
    assert avg.autocorr(1) > 0.15 > abs(end.autocorr(1))


def test_stats_flat_series():
    r = pd.Series(0.01, index=pd.date_range("2000-01-01", periods=24, freq="MS"))
    s = stats(r)
    assert abs(s["cagr"] - (1.01 ** 12 - 1)) < 1e-9 and s["max_dd"] == 0
