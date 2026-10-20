# Trend following, out of sample: 150 years of S&P 500 data and a tradable test

> Companion to the article [Trend Following Is Insurance, Not Alpha](https://www.guptagaurav.info/articles/trend-following-insurance-not-alpha). Author: Gaurav Gupta.

A simple trend rule (own the S&P 500 when it is above its 10-month average, otherwise hold T-bills) is tested two ways: on Robert Shiller's long-run monthly data, and on tradable SPY prices with dividends, T-bill cash and trading costs. The central finding is about **backtest integrity**: monthly-*average* prices, which most long-history studies use, overstate the rule's edge. On the same years and the same rule, about two-thirds of the Sharpe-ratio improvement over buy and hold disappears when tradable month-end prices are used. What remains is real but behaves like insurance: it cut the worst drawdown from -51% to -22% on SPY since 1997, at a cost of about 0.6 percentage points a year (about 2.0 points a year since 2007).

## Headline results

| Test | Rule | Trend CAGR | Buy-hold CAGR | Trend Sharpe | Buy-hold Sharpe | Trend max DD | Buy-hold max DD |
|---|---|---|---|---|---|---|---|
| Shiller monthly averages, 1872–2023 (cash 0%) | 10-month | 9.2% | 9.1% | 0.97 | 0.69 | -46% | -82% |
| SPY, monthly-average prices, 1997–2026 | 10-month | 10.9% | 9.8% | 0.95 | 0.62 | -19% | -49% |
| **SPY, month-end prices (tradable), 1997–2026** | **10-month** | **9.2%** | **9.8%** | **0.67** | **0.54** | **-22%** | **-51%** |
| SPY, month-end, 1997–2026 | 12-month momentum | 10.5% | 9.8% | 0.71 | 0.54 | -20% | -51% |
| SPY, month-end, June 2007 onward | 10-month | 8.7% | 10.7% | 0.70 | 0.64 | -22% | -51% |

Sharpe ratios are in excess of T-bills where bill data exist (SPY tests); the Shiller test assumes cash earns nothing. Costs: 5 bp per switch; a 25 bp stress test changes the tradable 10-month CAGR from 9.2% to 8.9%. Lag-1 autocorrelation of monthly returns: 0.19 with averaged SPY prices, 0.00 with month-end prices (0.27 in the Shiller series). Full output: `reports/metrics.json`.

## Data: real, public, pinned by checksum

| Data | Source | Notes |
|---|---|---|
| S&P Composite monthly price, dividends, 1871 onward | Robert Shiller, *Irrational Exuberance* online data; mirror [`datasets/s-and-p-500`](https://github.com/datasets/s-and-p-500) | Prices are monthly averages of daily closes. Dividends missing after June 2023 in the mirror, so the long test ends there. |
| SPY daily close and dividend events, 1996 onward | Yahoo Finance via [`defeatbeta/yahoo-finance-data`](https://huggingface.co/datasets/defeatbeta/yahoo-finance-data) (ODC-BY) | Unadjusted closes; total return built from ex-date dividends. |
| 3-month Treasury bill yield, daily, 1990 onward | U.S. Department of the Treasury daily par yield curve, via the same mirror | Cash and T-bill excess returns. |

`make ingest` downloads anything missing and stops if a file's sha256 differs from `configs/default.yaml` (downloaded 2026-10-20).

## Run it

```bash
pip install -r requirements.txt
make all     # ingest + run → reports/metrics.json, reports/figures/*.png
make test    # look-ahead, position-lag, cost and averaging unit tests
```

## Layout

```
configs/default.yaml     every rule, cost and window, fixed before results were examined; data checksums
src/trendoos/ingest.py   download + checksum gate
src/trendoos/pipeline.py returns, signals, backtests, tests A–E, business translation, figures
tests/                   unit tests
docs/ARCHITECTURE.md     pipeline and averaging-test flowcharts (Mermaid)
reports/                 metrics.json and figures
```

## Limits

One asset. The long-history test uses averaged prices and assumes zero cash return before 1990, so treat it as directional. Diversified trend programmes trade many markets with futures and behave differently. Results are not a forecast and not investment advice.

## Citations

- Shiller, R. J. *Irrational Exuberance* (Princeton University Press) and the accompanying online data, Yale University.
- Faber, M. T. (2007). "A Quantitative Approach to Tactical Asset Allocation." *The Journal of Wealth Management*, 9(4), 69–79.
- Moskowitz, T. J., Ooi, Y. H. and Pedersen, L. H. (2012). "Time series momentum." *Journal of Financial Economics*, 104(2), 228–250.
- Working, H. (1960). "Note on the correlation of first differences of averages in a random chain." *Econometrica*, 28(4), 916–918.
- Data mirror: defeatbeta, *yahoo-finance-data* (Hugging Face, ODC-BY).

All code, analysis and charts in this repository are the author's own. MIT licence.
