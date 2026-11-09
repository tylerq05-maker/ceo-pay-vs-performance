"""Portfolio backtest of the excess-pay signal (daily returns, annual rebalance).

    python -m src.backtest                    # 100-company sample
    FULL_UNIVERSE=1 python -m src.backtest    # all S&P 500 companies

Strategy (the direction Cooper, Gulen & Rau's finding implies): each year,
on 30 September, sort companies into fifths by excess pay (residual of
granted pay on TSR, size and sector, using only data public then). Go long
the most-UNDERPAID fifth and short the most-OVERPAID fifth, equal-weighted.

* Sep-2024 to Sep-2025: cohort A signal (pay FY2021-23)
* Sep-2025 to the last price date: cohort B signal (pay FY2022-24)

Reported per portfolio: annualised return and volatility, Sharpe ratio,
maximum drawdown, and a CAPM time-series regression
    (r_p - r_f) = alpha + beta (r_SPY - r_f) + e
with Newey-West (HAC, 5 lags) t-statistics. The long-short portfolio is
zero-investment, so its own return is regressed on the market excess return.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import config
from .market_data import load_prices, total_return_index
from .strategy import COHORTS, RF_CACHE, _risk_free  # noqa: F401  (_risk_free fills the ^IRX cache)

QS = ["Q1 most underpaid", "Q2", "Q3", "Q4", "Q5 most overpaid"]


def _daily_rf(index: pd.DatetimeIndex) -> pd.Series:
    if not RF_CACHE.exists():
        _risk_free("2024-01-01", "2024-01-31")
    irx = pd.read_csv(RF_CACHE, index_col=0, parse_dates=True).iloc[:, 0]
    return (irx / 100 / 252).reindex(index, method="ffill").fillna(0.0)


def portfolio_returns(cohorts: pd.DataFrame, rets: pd.DataFrame, end: str) -> pd.DataFrame:
    """Equal-weighted daily returns of each excess-pay quintile, rebalanced
    on each formation date; plus the long-short (Q1 minus Q5)."""
    forms = sorted(cohorts["formation"].unique())
    pieces = []
    for i, f in enumerate(forms):
        stop = forms[i + 1] if i + 1 < len(forms) else end
        window = rets.loc[(rets.index > pd.Timestamp(f)) & (rets.index <= pd.Timestamp(stop))]
        members = cohorts[cohorts["formation"] == f]
        cols = {}
        for q in QS:
            tick = [t for t in members.loc[members["quintile"] == q, "yf"] if t in window.columns]
            cols[q] = window[tick].mean(axis=1)
            cols[q + " n"] = pd.Series(len(tick), index=window.index)
        pieces.append(pd.DataFrame(cols))
    out = pd.concat(pieces).sort_index()
    out["Long underpaid / short overpaid"] = out["Q1 most underpaid"] - out["Q5 most overpaid"]
    return out


def stats_for(r: pd.Series, rf: pd.Series, mkt_ex: pd.Series, zero_investment: bool) -> dict:
    r = r.dropna()
    rf, mkt_ex = rf.reindex(r.index), mkt_ex.reindex(r.index)
    ex = r if zero_investment else r - rf
    growth = (1 + r).cumprod()
    dd = growth / growth.cummax() - 1
    X = sm.add_constant(mkt_ex.to_numpy())
    fit = sm.OLS(ex.to_numpy(), X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    years = len(r) / 252
    return {
        "days": int(len(r)), "years": float(years),
        "total_return": float(growth.iloc[-1] - 1),
        "ann_return": float(growth.iloc[-1] ** (1 / years) - 1),
        "ann_vol": float(r.std() * np.sqrt(252)),
        "sharpe": float(ex.mean() / ex.std() * np.sqrt(252)),
        "max_drawdown": float(dd.min()),
        "alpha_ann": float(fit.params[0] * 252), "alpha_t": float(fit.tvalues[0]), "alpha_p": float(fit.pvalues[0]),
        "beta": float(fit.params[1]), "beta_t": float(fit.tvalues[1]), "r2": float(fit.rsquared),
    }


def run() -> dict:
    P = config.DATA_PROCESSED
    sample = pd.read_csv(P / "sample.csv")
    yf_map = dict(zip(sample["ticker"], sample["yf_ticker"]))
    cohorts = pd.read_csv(P / "strategy_cohorts.csv")
    cohorts["yf"] = cohorts["ticker"].map(yf_map)
    prices = load_prices(sample["yf_ticker"].tolist())
    end = cohorts["end"].iloc[0]
    tris = {tk: total_return_index(px) for tk, px in prices.groupby("ticker")}
    rets = pd.DataFrame({tk: s.pct_change() for tk, s in tris.items()})
    rets = rets.loc[(rets.index > pd.Timestamp(min(cohorts["formation"]))) & (rets.index <= pd.Timestamp(end))]
    spy = total_return_index(load_prices(["SPY"])).pct_change().reindex(rets.index)
    rf = _daily_rf(rets.index)
    port = portfolio_returns(cohorts, rets, end)
    port["SPY"] = spy
    port["rf"] = rf
    mkt_ex = spy - rf

    res = {"start": str(port.index.min().date()), "end": str(port.index.max().date()),
           "rebalance_dates": sorted(cohorts["formation"].unique().tolist()),
           "n_per_quintile": {q: int(port[q + " n"].median()) for q in QS},
           "portfolios": {}}
    for name in QS + ["Long underpaid / short overpaid", "SPY"]:
        res["portfolios"][name] = stats_for(port[name], rf, mkt_ex, zero_investment=name.startswith("Long"))
    port.to_csv(P / "backtest_daily.csv")

    path = config.OUTPUT / "results.json"
    r = json.loads(path.read_text())
    r["backtest"] = res
    path.write_text(json.dumps(r, indent=2))
    ls = res["portfolios"]["Long underpaid / short overpaid"]
    print(f"[backtest] {config.scope_label()}: {res['start']} to {res['end']}, ~{res['n_per_quintile']['Q1 most underpaid']} stocks per fifth. "
          f"Long-short: total {100 * ls['total_return']:+.1f}%, Sharpe {ls['sharpe']:.2f}, "
          f"CAPM alpha {100 * ls['alpha_ann']:+.1f}%/yr (t = {ls['alpha_t']:.2f}), beta {ls['beta']:.2f}, "
          f"max drawdown {100 * ls['max_drawdown']:.1f}%")
    return res


if __name__ == "__main__":
    run()
