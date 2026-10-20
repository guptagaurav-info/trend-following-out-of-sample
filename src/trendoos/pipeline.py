"""Trend-following on the S&P 500: 150 years of history and a tradable out-of-sample test.

Two real, public data sets:
  A. Robert Shiller's monthly S&P Composite series (1871 onward), as mirrored by the
     datahub "s-and-p-500" core dataset. Prices are MONTHLY AVERAGES of daily closes.
  B. SPY daily closes and dividend events (Yahoo Finance via the defeatbeta mirror),
     plus the daily U.S. Treasury 3-month bill yield, 1996 onward.

Rules tested (decided before looking at results, see configs/default.yaml):
  - SMA10: hold equities when the month's price is above its 10-month average, else cash
    (Faber 2007).
  - TSMOM12: hold equities when the trailing 12-month total return is positive, else cash
    (Moskowitz, Ooi and Pedersen 2012, applied to a single asset).
The signal observed at the end of month t sets the position for month t+1. No look-ahead.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml


@dataclass
class Cfg:
    raw: Path
    out: Path
    cost_bps: float
    cost_bps_stress: float
    sma_months: int
    mom_months: int
    shiller_end: str
    pub_date: str
    allocation_usd: float


def load_cfg(path: str | Path) -> Cfg:
    c = yaml.safe_load(open(path))
    return Cfg(raw=Path(c["raw_dir"]), out=Path(c["out_dir"]), cost_bps=c["cost_bps"],
               cost_bps_stress=c["cost_bps_stress"], sma_months=c["sma_months"],
               mom_months=c["mom_months"], shiller_end=c["shiller_end"], pub_date=c["publication_date"],
               allocation_usd=c["allocation_usd"])


# ----------------------------------------------------------------------------- data
def shiller_monthly(cfg: Cfg) -> pd.DataFrame:
    """Monthly total-return index from Shiller averages: price change + dividend/12."""
    d = pd.read_csv(cfg.raw / "shiller_sp500_monthly.csv", parse_dates=["Date"])
    d = d[(d.Date <= cfg.shiller_end) & (d.SP500 > 0)].set_index("Date")
    assert (d.Dividend > 0).all(), "dividends missing inside the chosen window"
    px = d.SP500
    ret = px.pct_change() + (d.Dividend / 12.0) / px.shift(1)
    return pd.DataFrame({"price": px, "ret": ret, "cash": 0.0}).dropna()


def spy_daily(cfg: Cfg) -> pd.DataFrame:
    c = duckdb.connect()
    p = c.sql(f"select report_date d, cast(\"close\" as double) as px_close from '{cfg.raw/'prices.parquet'}' "
              "where symbol='SPY' order by 1").df()
    dv = c.sql(f"select report_date d, cast(amount as double) div from '{cfg.raw/'stock_dividend_events.parquet'}' "
               "where symbol='SPY'").df()
    tb = c.sql(f"select report_date d, cast(bc_3month as double) y from '{cfg.raw/'daily_treasury_yield.parquet'}'").df()
    for x in (p, dv, tb):
        x["d"] = pd.to_datetime(x["d"])
    p = p.rename(columns={"px_close": "close"}).set_index("d").sort_index()
    p["div"] = dv.groupby("d")["div"].sum().reindex(p.index).fillna(0.0)
    p["tr"] = (p.close + p["div"]) / p.close.shift(1) - 1  # dividend credited on ex-date
    tb = tb.set_index("d").sort_index()["y"]
    tb = tb / 100 if tb.max() > 1 else tb  # yields stored as decimals or percent
    p["bill"] = tb.reindex(p.index).ffill()
    return p.dropna(subset=["tr"])


def spy_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    """Two monthly views of the same SPY history: month-END (tradable) and month-AVERAGE (Shiller-style)."""
    g = daily.groupby(daily.index.to_period("M"))
    end_px = g.close.last()
    avg_px = g.close.mean()
    tr_end = g.tr.apply(lambda r: (1 + r).prod() - 1)
    # month-average total return: average-price change plus that month's dividends / prior average price
    div_m = g["div"].sum()
    tr_avg = avg_px.pct_change() + div_m / avg_px.shift(1)
    bill = g.bill.first() / 12.0  # bill yield known at the start of the month, earned over it
    m = pd.DataFrame({"end_px": end_px, "avg_px": avg_px, "tr_end": tr_end, "tr_avg": tr_avg, "cash": bill})
    m.index = m.index.to_timestamp()
    full = g.size() >= 15  # drop partial first/last months
    return m[full.values].iloc[1:]


# ----------------------------------------------------------------------------- rules
def signal(px: pd.Series, tr: pd.Series, rule: str, cfg: Cfg) -> pd.Series:
    if rule == "SMA10":
        s = px > px.rolling(cfg.sma_months).mean()
    elif rule == "TSMOM12":
        s = (1 + tr).rolling(cfg.mom_months).apply(np.prod, raw=True) - 1 > 0
    else:
        raise ValueError(rule)
    ready = px.rolling(max(cfg.sma_months, cfg.mom_months)).count() >= max(cfg.sma_months, cfg.mom_months)
    return s.astype(float).where(ready)


def backtest(ret: pd.Series, cash: pd.Series, sig: pd.Series, cost_bps: float) -> pd.DataFrame:
    pos = sig.shift(1)  # end-of-month t signal -> held during month t+1
    df = pd.DataFrame({"ret": ret, "cash": cash, "pos": pos}).dropna()
    trade = df.pos.diff().abs().fillna(0.0)
    df["strat"] = df.pos * df.ret + (1 - df.pos) * df.cash - trade * cost_bps / 1e4
    df["bh"] = df.ret
    df["switch"] = trade
    return df


def stats(r: pd.Series, cash: pd.Series | None = None, periods: int = 12) -> dict:
    eq = (1 + r).cumprod()
    yrs = len(r) / periods
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(periods)
    ex = r - (cash if cash is not None else 0.0)
    sharpe = ex.mean() / r.std() * np.sqrt(periods)
    dd = eq / eq.cummax() - 1
    worst12 = (1 + r).rolling(12).apply(np.prod, raw=True).min() - 1
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "max_dd": dd.min(), "worst_12m": worst12,
            "years": yrs, "start": str(r.index[0].date()), "end": str(r.index[-1].date())}


def summarize(bt: pd.DataFrame, label: str) -> dict:
    s = stats(bt.strat, bt.cash)
    b = stats(bt.bh, bt.cash)
    return {"label": label, "trend": s, "buy_hold": b, "time_invested": float(bt.pos.mean()),
            "switches_per_year": float(bt.switch.sum() / s["years"])}


def autocorr(r: pd.Series) -> float:
    return float(r.autocorr(1))


# ----------------------------------------------------------------------------- run
def run(cfg_path: str = "configs/default.yaml") -> dict:
    cfg = load_cfg(cfg_path)
    cfg.out.mkdir(parents=True, exist_ok=True)
    res: dict = {"config": {k: str(v) for k, v in cfg.__dict__.items()}}

    # A. 150 years on Shiller monthly averages (cash earns 0: no T-bill history before 1990 in this data)
    sh = shiller_monthly(cfg)
    res["shiller"] = {}
    for rule in ("SMA10", "TSMOM12"):
        bt = backtest(sh.ret, sh.cash, signal(sh.price, sh.ret, rule, cfg), cfg.cost_bps)
        res["shiller"][rule] = summarize(bt, f"Shiller monthly averages, {rule}")
        if rule == "SMA10":
            sh_bt = bt
    res["shiller_autocorr"] = autocorr(sh.ret)

    # B. Same rules on SPY: averaged prices vs tradable month-end prices, 1996 onward
    d = spy_daily(cfg)
    m = spy_monthly(d)
    res["spy"] = {}
    for rule in ("SMA10", "TSMOM12"):
        for view, px, tr in (("average", m.avg_px, m.tr_avg), ("month_end", m.end_px, m.tr_end)):
            # NB: averaged view earns averaged returns (what a monthly-average backtest reports)
            bt = backtest(tr, m.cash, signal(px, tr, rule, cfg), cfg.cost_bps)
            res["spy"][f"{rule}_{view}"] = summarize(bt, f"SPY {view} prices, {rule}")
        bt_x = backtest(m.tr_end, m.cash, signal(m.end_px, m.tr_end, rule, cfg), cfg.cost_bps_stress)
        res["spy"][f"{rule}_month_end_stress_cost"] = summarize(bt_x, f"SPY month-end, {rule}, {cfg.cost_bps_stress}bp")
    res["spy_autocorr"] = {"average": autocorr(m.tr_avg), "month_end": autocorr(m.tr_end)}

    # C. Post-publication window (Faber 2007): tradable SPY, month-end, T-bill cash
    post = m[m.index >= cfg.pub_date]
    pre_sig = signal(m.end_px, m.tr_end, "SMA10", cfg)
    bt_post = backtest(m.tr_end, m.cash, pre_sig, cfg.cost_bps)
    bt_post = bt_post[bt_post.index >= cfg.pub_date]
    res["post_publication_SMA10"] = summarize(bt_post, "SPY month-end SMA10 after publication")
    bt_post12 = backtest(m.tr_end, m.cash, signal(m.end_px, m.tr_end, "TSMOM12", cfg), cfg.cost_bps)
    res["post_publication_TSMOM12"] = summarize(bt_post12[bt_post12.index >= cfg.pub_date], "SPY month-end TSMOM12 after publication")

    # D. Crisis episodes (tradable, SMA10): peak-to-trough on each path
    episodes = {"Dot-com bust": ("2000-09-01", "2002-10-01"), "Global financial crisis": ("2007-11-01", "2009-03-01"),
                "COVID crash": ("2020-02-01", "2020-04-01"), "2022 rate shock": ("2022-01-01", "2022-10-01")}
    bt_all = backtest(m.tr_end, m.cash, pre_sig, cfg.cost_bps)
    ep = {}
    for k, (a, b) in episodes.items():
        w = bt_all.loc[a:b]
        ep[k] = {"buy_hold": float((1 + w.bh).prod() - 1), "trend": float((1 + w.strat).prod() - 1)}
    res["episodes"] = ep

    # E. Calendar-year scorecard (tradable, SMA10)
    yr = bt_all.groupby(bt_all.index.year)[["strat", "bh"]].apply(lambda x: (1 + x).prod() - 1)
    yr = yr[(yr.index > bt_all.index[0].year) & (yr.index < 2026)]
    res["years_trend_lagged_by_10pct_plus"] = [int(y) for y in yr.index[(yr.bh - yr.strat) > 0.10]]
    res["years_trend_saved_10pct_plus"] = [int(y) for y in yr.index[(yr.strat - yr.bh) > 0.10]]

    # Business translation on an illustrative allocation
    a = cfg.allocation_usd
    pe = res["spy"]["SMA10_month_end"]
    res["business"] = {
        "allocation_usd": a,
        "max_loss_buy_hold_usd": a * pe["buy_hold"]["max_dd"],
        "max_loss_trend_usd": a * pe["trend"]["max_dd"],
        "annual_return_give_up": pe["buy_hold"]["cagr"] - pe["trend"]["cagr"],
        "annual_cost_usd": a * (pe["buy_hold"]["cagr"] - pe["trend"]["cagr"]),
    }

    json.dump(res, open(cfg.out / "metrics.json", "w"), indent=2, default=float)
    _figures(cfg, sh_bt, bt_all, yr, res)
    return res


# ----------------------------------------------------------------------------- figures
def _years_axis(ax, step=10):
    from matplotlib.ticker import MultipleLocator, FuncFormatter
    ax.xaxis.set_major_locator(MultipleLocator(step))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))


def _figures(cfg: Cfg, sh_bt: pd.DataFrame, bt: pd.DataFrame, yr: pd.DataFrame, res: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    fig_dir = cfg.out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    blue, gold, grey = "#3A6A9A", "#9A7F2E", "#8A8880"

    # 1. 150-year drawdowns (Shiller)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    t = sh_bt.index.year + (sh_bt.index.month - 1) / 12
    for col, lab, c in (("bh", "Buy and hold", grey), ("strat", "10-month trend rule", blue)):
        eq = (1 + sh_bt[col]).cumprod()
        ax.plot(t, (eq / eq.cummax() - 1) * 100, color=c, lw=1.1, label=lab)
    ax.set_title("Drawdown from previous peak, S&P 500 total return, 1872–2023 (Shiller monthly data)")
    ax.set_ylabel("Drawdown (%)"); _years_axis(ax, 10); ax.set_xlim(t[0] - 1, t[-1] + 1)
    ax.set_ylim(top=3); ax.axhline(0, color="#1A1A1F", lw=0.6)
    ax.legend(loc="lower right", frameon=True, facecolor="white", edgecolor="#DDD9CE", framealpha=0.95)
    fig.tight_layout(); fig.savefig(fig_dir / "drawdowns_150y.png", dpi=160); plt.close(fig)

    # 2. The averaging illusion (SPY 1997+): Sharpe by price view
    s = res["spy"]
    labels = ["10-month trend", "12-month momentum"]
    avg = [s["SMA10_average"]["trend"]["sharpe"], s["TSMOM12_average"]["trend"]["sharpe"]]
    end = [s["SMA10_month_end"]["trend"]["sharpe"], s["TSMOM12_month_end"]["trend"]["sharpe"]]
    bh = s["SMA10_month_end"]["buy_hold"]["sharpe"]
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    x = np.arange(2)
    ax.bar(x - 0.18, avg, 0.36, color=gold, label="Backtest on monthly-average prices")
    ax.bar(x + 0.18, end, 0.36, color=blue, label="Tradable: month-end prices")
    ax.axhline(bh, color=grey, ls="--", lw=1.2, label=f"Buy and hold SPY ({bh:.2f})")
    for i in range(2):
        ax.text(x[i] - 0.18, avg[i] + 0.01, f"{avg[i]:.2f}", ha="center", va="bottom")
        ax.text(x[i] + 0.18, end[i] + 0.01, f"{end[i]:.2f}", ha="center", va="bottom")
    ax.set_xticks(x, labels); ax.set_ylabel("Sharpe ratio (excess of T-bills)")
    ax.set_ylim(0, max(avg + end) * 1.35)
    ax.set_title("Same rule, same years: averaged prices flatter trend-following (SPY, 1997–2026)")
    ax.legend(frameon=False, loc="upper center", ncol=2, fontsize=9); fig.tight_layout()
    fig.savefig(fig_dir / "averaging_illusion.png", dpi=160); plt.close(fig)

    # 3. Tradable equity curves (log) with shaded cash periods
    fig, ax = plt.subplots(figsize=(11, 4.6))
    t = bt.index.year + (bt.index.month - 1) / 12
    ax.plot(t, (1 + bt.bh).cumprod(), color=grey, lw=1.2, label="Buy and hold SPY")
    ax.plot(t, (1 + bt.strat).cumprod(), color=blue, lw=1.4, label="10-month trend rule (cash in T-bills)")
    out = bt.pos == 0
    ax.fill_between(t, 0, 1, where=out.values, transform=ax.get_xaxis_transform(), color=gold, alpha=0.15, lw=0, label="Rule in cash")
    from matplotlib.ticker import FixedLocator, FuncFormatter as FF
    ax.set_yscale("log"); ax.set_ylabel("Growth of $1 (log scale)"); _years_axis(ax, 2)
    ax.yaxis.set_major_locator(FixedLocator([1, 2, 4, 8, 16])); ax.yaxis.set_minor_locator(FixedLocator([]))
    ax.yaxis.set_major_formatter(FF(lambda v, _: f"${v:g}")); ax.set_xlim(t[0] - 0.3, t[-1] + 0.3)
    ax.set_title("Tradable test on SPY with dividends, T-bill cash and 5 bp costs, 1997–2026")
    ax.legend(frameon=False, loc="upper left"); fig.tight_layout()
    fig.savefig(fig_dir / "spy_equity_curves.png", dpi=160); plt.close(fig)

    # 4. Calendar-year difference
    fig, ax = plt.subplots(figsize=(11, 4.2))
    diff = (yr.strat - yr.bh) * 100
    ax.bar(yr.index, diff, color=[blue if v >= 0 else gold for v in diff])
    ax.axhline(0, color="#1A1A1F", lw=0.8)
    ax.set_title("Trend rule minus buy and hold, by calendar year (SPY, tradable)")
    ax.set_ylabel("Return difference (percentage points)"); _years_axis(ax, 2); ax.set_xlim(yr.index[0] - 0.8, yr.index[-1] + 0.8)
    fig.tight_layout(); fig.savefig(fig_dir / "calendar_year_difference.png", dpi=160); plt.close(fig)


if __name__ == "__main__":
    import sys
    r = run(sys.argv[1] if len(sys.argv) > 1 else "configs/default.yaml")
    print(json.dumps({k: r[k] for k in ("shiller", "spy_autocorr", "shiller_autocorr")}, indent=1, default=float)[:3000])
