# How this project works

Two diagrams:
1. **Pipeline**: every step, its source file, and the logic inside it.
2. **The averaging test**: why the same rule gives two different answers, and which one is tradable.

Colour key: **blue** = external data source · **lavender** = code step · **yellow** = rule or model · **red** = check or gate · **grey** = output

## 1. Pipeline (what `make all` runs)

```mermaid
flowchart TD
    A["SOURCE: Robert Shiller S&P Composite, monthly, 1871 onward<br/>price = average of daily closes · dividends<br/>mirror: github.com/datasets/s-and-p-500"]
    B["SOURCE: SPY daily closes + dividend events, 1996 onward<br/>U.S. Treasury 3-month bill yield, daily<br/>mirror: huggingface.co/datasets/defeatbeta/yahoo-finance-data"]
    I{"ingest.py<br/>sha256 matches config?"}
    A --> I
    B --> I
    I -- "no" --> X["Stop: source changed"]
    I -- "yes" --> L

    subgraph L["Load and build returns · pipeline.py"]
      L1["Shiller: total return = price change + dividend/12<br/>window 1871–2023-06 (last month with dividends)<br/>cash earns 0% (no bill history in this file)"]
      L2["SPY: total return with dividend on ex-date<br/>two monthly views: month-END close and month-AVERAGE close<br/>cash earns the 3-month bill yield"]
    end

    subgraph R["Rules fixed in configs/default.yaml"]
      R1["SMA10: invested if price > 10-month average (Faber 2007)"]
      R2["TSMOM12: invested if trailing 12-month return > 0<br/>(Moskowitz, Ooi & Pedersen 2012)"]
      R3["Signal at end of month t → position in month t+1<br/>5 bp per switch · 25 bp stress test"]
    end

    subgraph T["Tests"]
      T1["150 years on Shiller averages"]
      T2{"Averaging test on SPY 1997–2026:<br/>average prices vs month-end prices"}
      T3["Post-publication window, June 2007 onward"]
      T4["Crisis episodes and calendar-year scorecard"]
    end

    O["reports/metrics.json · reports/figures/*.png"]
    L --> R --> T --> O

    classDef src fill:#dbe8ff,stroke:#1f5fbf,color:#0b1f44
    classDef step fill:#ece8ff,stroke:#6b5fbf,color:#1d1640
    classDef rule fill:#fff4cc,stroke:#b38f00,color:#3d3000
    classDef gate fill:#ffe0e0,stroke:#c03030,color:#400000
    classDef out fill:#eeeeee,stroke:#777,color:#222
    class A,B src
    class L1,L2,T1,T3,T4 step
    class R1,R2,R3 rule
    class I,X,T2 gate
    class O out
```

## 2. The averaging test

```mermaid
flowchart LR
    D["Daily SPY closes"] --> AV["Month-AVERAGE price<br/>(how long-history data is built)"]
    D --> EN["Month-END price<br/>(what you can actually trade at)"]
    AV --> SA["Signal uses the average of month t,<br/>which already contains late-month prices"]
    SA --> RA["Return judged from avg(t) to avg(t+1):<br/>half of it overlaps the signal window"]
    RA --> BA["Result: positive return autocorrelation (0.19)<br/>Sharpe 0.95 for the 10-month rule"]
    EN --> SE["Signal at the close of the last day of month t"]
    SE --> RE["Return earned from that close to the next month-end close"]
    RE --> BE["Result: no autocorrelation (0.00)<br/>Sharpe 0.67 for the same rule"]
    classDef src fill:#dbe8ff,stroke:#1f5fbf,color:#0b1f44
    classDef gate fill:#ffe0e0,stroke:#c03030,color:#400000
    classDef ok fill:#e3f3e3,stroke:#3a8a3a,color:#103010
    class D src
    class AV,SA,RA,BA gate
    class EN,SE,RE,BE ok
```
