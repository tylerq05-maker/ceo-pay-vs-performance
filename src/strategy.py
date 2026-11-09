"""Strategy test - does CEO "overpay" predict future stock returns?

Motivation: Cooper, Gulen & Rau ("Performance for Pay?", 1994-2011 data) found
that firms paying CEOs the most *excess* pay (pay unexplained by size/industry)
earned negative abnormal returns afterwards. We test whether the same signal
works out-of-sample in 2024-2026, using only information an investor could
have had at the formation date.

Design (point-in-time, two cohorts):
* Cohort A - pay window FY2021-FY2023, formed 2024-09-30 (after every FY2023
  proxy was filed), held to the last price date (~2.1 years).
* Cohort B - pay window FY2022-FY2024, formed 2025-09-30 (~1.1 years).
For each cohort we refit the primary model (ln avg SCT pay ~ TSR + ln start-of-
window market cap + sector FE) on that window only and take the residual as the
"excess pay" signal. Forward performance is measured four ways:
  raw TSR, TSR minus SPY, CAPM abnormal return (beta from 2 years of weekly
  returns before formation, T-bill as the risk-free rate), and sector-adjusted.
Tests: residual-quintile portfolios (Q5 most overpaid minus Q1), Spearman rank
IC, and a cross-sectional regression with size, momentum and sector controls.

Caveats (stated in the outputs): current-constituent sample (survivorship),
PvP values for earlier years taken from the latest proxy (rarely restated),
n ~ 95-99 per cohort, one holding period per cohort.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import yfinance as yf
from scipy import stats

from . import config
from .analysis import corr, winsorize
from .market_data import _at, load_prices, total_return_index, tsr_between

COHORTS = {
    "A": {"fys": (2021, 2022, 2023), "formation": "2024-09-30"},
    "B": {"fys": (2022, 2023, 2024), "formation": "2025-09-30"},
}
RF_CACHE = config.RAW_MARKET / "irx.csv"
BOOT = 5000


def _risk_free(start: str, end: str) -> float:
    """Compounded 13-week T-bill return between two dates (cached ^IRX)."""
    if RF_CACHE.exists():
        irx = pd.read_csv(RF_CACHE, index_col=0, parse_dates=True).iloc[:, 0]
    else:
        raw = yf.download("^IRX", start="2019-01-01", auto_adjust=False, progress=False)
        irx = raw["Close"].squeeze().dropna()
        irx.index = irx.index.tz_localize(None) if irx.index.tz is not None else irx.index
        irx.to_frame("irx").to_csv(RF_CACHE)
    s = irx.loc[start:end] / 100 / 252
    return float(np.prod(1 + s.to_numpy()) - 1)


def _beta(tri: pd.Series, mkt: pd.Series, formation: str) -> float:
    """Market beta from 104 weekly returns ending at the formation date."""
    f = pd.Timestamp(formation)
    a = tri.loc[f - pd.DateOffset(years=2):f].resample("W-FRI").last().pct_change()
    b = mkt.loc[f - pd.DateOffset(years=2):f].resample("W-FRI").last().pct_change()
    df = pd.concat([a, b], axis=1).dropna()
    if len(df) < 52:
        return float("nan")
    cov = np.cov(df.iloc[:, 0], df.iloc[:, 1])
    return float(cov[0, 1] / cov[1, 1])


def build_cohort(name: str, spec: dict, pvp: pd.DataFrame, sample: pd.DataFrame, fun: pd.DataFrame,
                 tris: dict, prices: pd.DataFrame, spy: pd.Series, end: str) -> pd.DataFrame:
    tick = dict(zip(sample["ticker"], sample["yf_ticker"]))
    sector = dict(zip(sample["ticker"], sample["sector"]))
    mcap_now = dict(zip(fun["ticker"], fun["yf_marketCap"]))
    last_close = prices.groupby("ticker").apply(lambda d: d.sort_values("date")["close"].iloc[-1],
                                                include_groups=False)
    rows = []
    for tk, g in pvp.groupby("ticker"):
        g = g[g["fy"].isin(spec["fys"])].sort_values("fy")
        yt = tick.get(tk, tk)
        if len(g) < len(spec["fys"]) or yt not in tris:
            continue
        tri = tris[yt]
        start = date.fromisoformat(g["start"].iloc[0]) - timedelta(days=1)
        wend = g["end"].iloc[-1]
        if pd.Timestamp(wend) >= pd.Timestamp(spec["formation"]):
            continue  # pay window must be fully disclosed before formation
        px = prices[prices["ticker"] == yt].set_index("date")["close"]
        p0 = _at(px, start)
        tsr = tsr_between(tri, start, wend)
        rows.append({
            "cohort": name, "ticker": tk, "sector": sector.get(tk),
            "window_start": start.isoformat(), "window_end": wend,
            "sct_avg": g["ceo_sct_total"].mean(),
            "tsr_window": tsr, "tsr_window_ann": (1 + tsr) ** (1 / len(spec["fys"])) - 1,
            "mcap_start": mcap_now.get(tk, np.nan) * p0 / last_close.get(yt, np.nan),
            "ceo_change": bool(g["multi_peo_year"].fillna(False).astype(bool).any()),
            "fwd_ret": tsr_between(tri, spec["formation"], end),
            "beta": _beta(tri, spy, spec["formation"]),
        })
    d = pd.DataFrame(rows).dropna(subset=["sct_avg", "tsr_window", "mcap_start", "fwd_ret"])
    # Residual "excess pay" signal from a model fitted on this window only
    d["ln_pay"] = np.log(d["sct_avg"])
    d["ln_mcap"] = np.log(d["mcap_start"])
    d["tsr_pp_w"] = winsorize(100 * d["tsr_window_ann"])
    res = smf.ols("ln_pay ~ tsr_pp_w + ln_mcap + C(sector)", data=d).fit(cov_type="HC3")
    d["excess_pay"] = res.resid
    d["model_r2"] = res.rsquared
    # Forward performance measures
    r_m = tsr_between(spy, spec["formation"], end)
    r_f = _risk_free(spec["formation"], end)
    d["spy_ret"] = r_m
    d["rf_ret"] = r_f
    d["excess_vs_spy"] = d["fwd_ret"] - r_m
    d["capm_abnormal"] = (d["fwd_ret"] - r_f) - d["beta"] * (r_m - r_f)
    d["sector_adj"] = d["fwd_ret"] - d.groupby("sector")["fwd_ret"].transform("median")
    d["quintile"] = pd.qcut(d["excess_pay"].rank(method="first"), 5,
                            labels=["Q1 most underpaid", "Q2", "Q3", "Q4", "Q5 most overpaid"])
    med = d["tsr_window_ann"].median()
    d["misaligned"] = (d["excess_pay"] > 0) & (d["tsr_window_ann"] < med)
    d["formation"] = spec["formation"]
    d["end"] = end
    d["years_held"] = (pd.Timestamp(end) - pd.Timestamp(spec["formation"])).days / 365.25
    return d


def _boot_diff(a: np.ndarray, b: np.ndarray, rng) -> tuple[float, float]:
    diffs = [rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(BOOT)]
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def evaluate(d: pd.DataFrame, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    out = {"n": int(len(d)), "formation": d["formation"].iloc[0], "end": d["end"].iloc[0],
           "years_held": float(d["years_held"].iloc[0]), "spy_ret": float(d["spy_ret"].iloc[0]),
           "rf_ret": float(d["rf_ret"].iloc[0]), "signal_model_r2": float(d["model_r2"].iloc[0]),
           "measures": {}}
    for m in ("fwd_ret", "excess_vs_spy", "capm_abnormal", "sector_adj"):
        dd = d.dropna(subset=[m])
        q = dd.groupby("quintile", observed=True)[m].agg(["mean", "median", "size"])
        q5 = dd.loc[dd["quintile"] == "Q5 most overpaid", m].to_numpy()
        q1 = dd.loc[dd["quintile"] == "Q1 most underpaid", m].to_numpy()
        t, p = stats.ttest_ind(q5, q1, equal_var=False)
        lo, hi = _boot_diff(q5, q1, rng)
        mis = dd.loc[dd["misaligned"], m].to_numpy()
        rest = dd.loc[~dd["misaligned"], m].to_numpy()
        tm, pm = stats.ttest_ind(mis, rest, equal_var=False)
        # Outlier-robust versions: a few "moonshot" stocks (e.g. Bloom Energy
        # +1,798%, Moderna +900% after its Aug-2026 melanoma-vaccine data) can
        # dominate equal-weighted means in a 19-stock quintile.
        w = winsorize(dd[m], 0.05, 0.95)
        q5w = w[dd["quintile"] == "Q5 most overpaid"].to_numpy()
        q1w = w[dd["quintile"] == "Q1 most underpaid"].to_numpy()
        tw, pw = stats.ttest_ind(q5w, q1w, equal_var=False)
        u, pu = stats.mannwhitneyu(q5, q1, alternative="two-sided")
        lo_w, hi_w = _boot_diff(q5w, q1w, rng)
        out["measures"][m] = {
            "quintile_mean": {k: float(v) for k, v in q["mean"].items()},
            "quintile_median": {k: float(v) for k, v in q["median"].items()},
            "quintile_mean_winsor": {k: float(v) for k, v in w.groupby(dd["quintile"], observed=True).mean().items()},
            "quintile_n": {k: int(v) for k, v in q["size"].items()},
            "q5_minus_q1": float(q5.mean() - q1.mean()), "t": float(t), "p": float(p),
            "boot_ci": [lo, hi],
            "q5_minus_q1_median": float(np.median(q5) - np.median(q1)), "mannwhitney_p": float(pu),
            "q5_minus_q1_winsor": float(q5w.mean() - q1w.mean()), "p_winsor": float(pw),
            "boot_ci_winsor": [lo_w, hi_w],
            "top_movers": dd.nlargest(3, m)[["ticker", "quintile", m]].astype({m: float}).to_dict(orient="records"),
            "rank_ic": corr(dd["excess_pay"], dd[m]),
            "misaligned_minus_rest": float(mis.mean() - rest.mean()), "misaligned_p": float(pm),
            "n_misaligned": int(len(mis)),
        }
    dd = d.dropna(subset=["capm_abnormal"]).copy()
    dd["mom"] = winsorize(100 * dd["tsr_window_ann"])
    dd["y"] = winsorize(100 * dd["capm_abnormal"])
    res = smf.ols("y ~ excess_pay + ln_mcap + mom + C(sector)", data=dd).fit(cov_type="HC3")
    out["regression_capm"] = {"coef_excess_pay": float(res.params["excess_pay"]),
                              "se": float(res.bse["excess_pay"]), "p": float(res.pvalues["excess_pay"]),
                              "r2": float(res.rsquared), "n": int(res.nobs),
                              "note": "abnormal return in pp per 1 log-point of excess pay (winsorised)"}
    return out


def run() -> dict:
    P = config.DATA_PROCESSED
    sample = pd.read_csv(P / "sample.csv")
    pvp = pd.read_csv(P / "pvp_company_years.csv")
    fun = pd.read_csv(P / "fundamentals.csv")
    prices = load_prices(sample["yf_ticker"].tolist())
    end = prices.groupby("ticker")["date"].max().min().strftime("%Y-%m-%d")
    spy_px = load_prices(["SPY"])
    spy = total_return_index(spy_px)
    tris = {tk: total_return_index(px) for tk, px in prices.groupby("ticker")}
    frames, results = [], {"end_date": end, "cohorts": {}}
    for name, spec in COHORTS.items():
        d = build_cohort(name, spec, pvp, sample, fun, tris, prices, spy, end)
        frames.append(d)
        results["cohorts"][name] = {"pay_window": f"FY{spec['fys'][0]}-FY{spec['fys'][-1]}", **evaluate(d)}
    allc = pd.concat(frames, ignore_index=True)
    allc.to_csv(P / "strategy_cohorts.csv", index=False)
    # Persist into results.json next to the main analysis
    path = config.ROOT / "output" / "results.json"
    r = json.loads(path.read_text())
    r["strategy"] = results
    path.write_text(json.dumps(r, indent=2))
    for k, v in results["cohorts"].items():
        c = v["measures"]["capm_abnormal"]
        print(f"[strategy] cohort {k} ({v['pay_window']}, formed {v['formation']}, {v['years_held']:.1f}y, n={v['n']}): "
              f"CAPM abnormal Q5-Q1: median {100 * c['q5_minus_q1_median']:+.1f}pp (MW p={c['mannwhitney_p']:.2f}), "
              f"winsorised mean {100 * c['q5_minus_q1_winsor']:+.1f}pp (p={c['p_winsor']:.2f}), raw mean "
              f"{100 * c['q5_minus_q1']:+.1f}pp; rank IC {c['rank_ic']['spearman_rho']:+.2f} (p={c['rank_ic']['spearman_p']:.2f}); "
              f"regression p={v['regression_capm']['p']:.2f}")
    return results


if __name__ == "__main__":
    run()
