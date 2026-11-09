"""Phase 4b - Statistical analysis of CEO pay vs. TSR.

Every number quoted in the report is written to ``output/results.json`` by
this module, and the report is rendered from that file, so all figures trace
back to the data.

Models (cross-section, one row per company, OLS with HC3 robust SEs):
  A1  ln(avg SCT pay)            ~ TSR
  A2  ln(avg SCT pay)            ~ TSR + ln(start-of-window market cap)
  A3  ln(avg SCT pay)            ~ TSR + ln(mcap) + sector fixed effects   <- outliers
  B1-B3 same with asinh(avg CAP, $M) as the dependent variable
TSR = annualised independent TSR over the same fiscal window, in percentage
points, winsorised at the 2.5th/97.5th percentiles (raw TSR used in a
robustness check).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from . import config

WINSOR = (0.025, 0.975)
OUT_TABLES = config.OUTPUT / "tables"
OUT_TABLES.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def winsorize(s: pd.Series, lo: float = WINSOR[0], hi: float = WINSOR[1]) -> pd.Series:
    ql, qh = s.quantile(lo), s.quantile(hi)
    return s.clip(ql, qh)


def prepare(m: pd.DataFrame, n: int) -> pd.DataFrame:
    d = m.copy()
    d["tsr_pp"] = 100 * d[f"tsr_{n}y_ann"]
    d["tsr_pp_w"] = winsorize(d["tsr_pp"])
    d["ln_pay"] = d[f"ln_sct_avg_{n}y"]
    d["asinh_cap"] = np.arcsinh(d[f"cap_avg_{n}y"] / 1e6)
    d["ln_mcap"] = d[f"ln_mcap_start_{n}y"]
    d["rel_tsr_pp"] = winsorize(100 * ((1 + d[f"tsr_{n}y"]) ** (1 / n) - (1 + d[f"peer_tsr_{n}y"]) ** (1 / n)))
    d["sector_fe"] = d["sector"].astype("category")
    keep = d[["ln_pay", "asinh_cap", "tsr_pp_w", "ln_mcap"]].notna().all(axis=1)
    return d[keep].copy()


def fit(formula: str, data: pd.DataFrame):
    return smf.ols(formula, data=data).fit(cov_type="HC3")


def summarize(res, key: str = "tsr_pp_w") -> dict:
    out = {"n": int(res.nobs), "r2": float(res.rsquared), "adj_r2": float(res.rsquared_adj),
           "f_pvalue": float(res.f_pvalue) if res.f_pvalue == res.f_pvalue else None, "coefs": {}}
    for name in res.params.index:
        if name.startswith("C(") or name.startswith("sector_fe"):
            continue
        out["coefs"][name] = {"coef": float(res.params[name]), "se": float(res.bse[name]),
                              "t": float(res.tvalues[name]), "p": float(res.pvalues[name]),
                              "ci_lo": float(res.conf_int().loc[name, 0]),
                              "ci_hi": float(res.conf_int().loc[name, 1])}
    if key in res.params:
        b = res.params[key]
        # effect of +10pp annual TSR on pay, in % (log model) or approx % (asinh)
        out["pct_pay_per_10pp_tsr"] = float(100 * (np.exp(10 * b) - 1))
    if "ln_mcap" in res.params:
        out["size_elasticity"] = float(res.params["ln_mcap"])
    return out


def corr(x: pd.Series, y: pd.Series) -> dict:
    ok = x.notna() & y.notna()
    x, y = x[ok], y[ok]
    pr, pp = stats.pearsonr(x, y)
    sr, sp = stats.spearmanr(x, y)
    return {"n": int(ok.sum()), "pearson_r": float(pr), "pearson_p": float(pp),
            "spearman_rho": float(sr), "spearman_p": float(sp)}


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------
def descriptives(m: pd.DataFrame, panel: pd.DataFrame) -> dict:
    n = config.PRIMARY_WINDOW_YEARS
    latest = m.dropna(subset=["sct_latest"])
    return {
        "n_companies": int(len(m)),
        "n_with_primary_window": int(m[f"tsr_{n}y"].notna().sum()),
        "n_company_years": int(len(panel)),
        "n_sectors": int(m["sector"].nunique()),
        "latest_fy_counts": {str(k): int(v) for k, v in m["latest_fy"].value_counts().items()},
        "median_sct_latest": float(latest["sct_latest"].median()),
        "mean_sct_latest": float(latest["sct_latest"].mean()),
        "median_cap_latest": float(latest["cap_latest"].median()),
        "max_sct_latest": float(latest["sct_latest"].max()),
        "max_sct_latest_ticker": str(latest.loc[latest["sct_latest"].idxmax(), "ticker"]),
        "median_sct_3y": float(m["sct_avg_3y"].median()),
        "median_cap_3y": float(m["cap_avg_3y"].median()),
        "p10_sct_3y": float(m["sct_avg_3y"].quantile(.1)),
        "p90_sct_3y": float(m["sct_avg_3y"].quantile(.9)),
        "median_tsr_3y_ann": float(m["tsr_3y_ann"].median()),
        "median_tsr_1y": float(m["tsr_1y"].median()),
        "median_tsr_5y_ann": float(m["tsr_5y_ann"].median()),
        "share_negative_tsr_3y": float((m["tsr_3y"] < 0).mean()),
        "n_negative_cap_years": int((panel["ceo_cap"] < 0).sum()),
        "n_ceo_change_3y": int(m["ceo_change_3y"].fillna(False).astype(bool).sum()),
        "n_multi_peo_companies": int(panel.groupby("ticker")["multi_peo_year"].any().sum()),
        "median_mcap_now": float(m["mcap_now"].median()),
        "cap_to_sct_median_3y": float(m["cap_to_sct_3y"].median()),
        "pct_ceo_years_cap_above_sct": float((panel["ceo_cap"] > panel["ceo_sct_total"]).mean()),
        "winsor_bounds_3y_pp": [float(100 * m["tsr_3y_ann"].quantile(WINSOR[0])),
                                float(100 * m["tsr_3y_ann"].quantile(WINSOR[1]))],
    }


def correlations(m: pd.DataFrame) -> dict:
    out = {}
    for n in config.WINDOWS:
        d = prepare(m, n)
        out[f"{n}y"] = {
            "sct_vs_tsr": corr(d["ln_pay"], d["tsr_pp_w"]),
            "cap_vs_tsr": corr(d["asinh_cap"], d["tsr_pp_w"]),
            "sct_vs_mcap": corr(d["ln_pay"], d["ln_mcap"]),
            "cap_to_sct_vs_tsr": corr(d[f"cap_to_sct_{n}y"], d["tsr_pp_w"]),
        }
    return out


def regressions(m: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    out, tables = {}, []
    specs = {
        "1_simple": "{y} ~ tsr_pp_w",
        "2_size": "{y} ~ tsr_pp_w + ln_mcap",
        "3_size_sector": "{y} ~ tsr_pp_w + ln_mcap + C(sector)",
    }
    for n in config.WINDOWS:
        d = prepare(m, n)
        for yname, y in (("sct", "ln_pay"), ("cap", "asinh_cap")):
            for sname, f in specs.items():
                res = fit(f.format(y=y), d)
                key = f"{yname}_{n}y_{sname}"
                out[key] = summarize(res)
                c = out[key]["coefs"]["tsr_pp_w"]
                tables.append({"model": key, "dep_var": y, "window": f"{n}y", "spec": sname,
                               "n": out[key]["n"], "tsr_coef": c["coef"], "tsr_se": c["se"],
                               "tsr_p": c["p"], "ln_mcap_coef": out[key]["coefs"].get("ln_mcap", {}).get("coef"),
                               "ln_mcap_p": out[key]["coefs"].get("ln_mcap", {}).get("p"),
                               "r2": out[key]["r2"], "adj_r2": out[key]["adj_r2"],
                               "pct_pay_per_10pp_tsr": out[key].get("pct_pay_per_10pp_tsr")})
    # Robustness on the primary window ------------------------------------
    n = config.PRIMARY_WINDOW_YEARS
    d = prepare(m, n)
    rob = {}
    d["tsr_pp_raw"] = d["tsr_pp"]
    rob["raw_tsr"] = summarize(fit("ln_pay ~ tsr_pp_raw + ln_mcap + C(sector)", d), key="tsr_pp_raw")
    no_change = d[~d[f"ceo_change_{n}y"].fillna(False).astype(bool)]
    rob["excl_ceo_change"] = summarize(fit("ln_pay ~ tsr_pp_w + ln_mcap + C(sector)", no_change))
    d2 = d.dropna(subset=["rel_tsr_pp"])
    rob["peer_relative_tsr"] = summarize(fit("ln_pay ~ rel_tsr_pp + ln_mcap + C(sector)", d2), key="rel_tsr_pp")
    d3 = d.copy()
    d3["ln_mcap"] = d3["ln_mcap_now"]
    rob["current_mcap"] = summarize(fit("ln_pay ~ tsr_pp_w + ln_mcap + C(sector)", d3))
    d4 = d.dropna(subset=["revenue_latest"]).copy()
    d4["ln_rev"] = np.log(d4["revenue_latest"])
    rob["revenue_size"] = summarize(fit("ln_pay ~ tsr_pp_w + ln_rev + C(sector)", d4))
    d5 = d.copy()
    d5["ln_seat"] = np.log(d5[f"seat_sct_avg_{n}y"].where(d5[f"seat_sct_avg_{n}y"] > 0))
    rob["ceo_seat_pay"] = summarize(fit("ln_seat ~ tsr_pp_w + ln_mcap + C(sector)", d5))
    # Rank-rank regression (fully outlier-robust)
    d6 = d.copy()
    d6["pay_rank"] = d6["ln_pay"].rank(pct=True)
    d6["tsr_rank"] = d6["tsr_pp"].rank(pct=True)
    d6["mcap_rank"] = d6["ln_mcap"].rank(pct=True)
    rob["rank_rank"] = summarize(fit("pay_rank ~ tsr_rank + mcap_rank", d6), key="tsr_rank")
    # Exclude CEOs with no equity grant at all in the window (founder / lumpy
    # multi-year grant cases such as AMZN, PLTR, COIN, META): their SCT pay
    # is near-zero by design and they are high-leverage points.
    d7 = d[d["mix_equity"].fillna(0) > 0.05]
    rob["excl_no_equity_grants"] = summarize(fit("ln_pay ~ tsr_pp_w + ln_mcap + C(sector)", d7))
    rob["excl_no_equity_grants"]["excluded"] = sorted(d.loc[d["mix_equity"].fillna(0) <= 0.05, "ticker"].tolist())
    out["robustness_3y"] = rob
    for k, v in rob.items():
        coef_key = next((c for c in v["coefs"] if c not in ("Intercept", "ln_mcap", "ln_rev")), None)
        c = v["coefs"].get(coef_key, {})
        tables.append({"model": f"robust_{k}", "dep_var": "ln_pay", "window": f"{n}y", "spec": k,
                       "n": v["n"], "tsr_coef": c.get("coef"), "tsr_se": c.get("se"), "tsr_p": c.get("p"),
                       "r2": v["r2"], "adj_r2": v["adj_r2"],
                       "pct_pay_per_10pp_tsr": v.get("pct_pay_per_10pp_tsr")})
    return out, pd.DataFrame(tables)


def sector_analysis(m: pd.DataFrame) -> pd.DataFrame:
    n = config.PRIMARY_WINDOW_YEARS
    d = prepare(m, n)
    rows = []
    for sec, g in d.groupby("sector"):
        rec = {"sector": sec, "n": len(g), "median_sct_3y_musd": g[f"sct_avg_{n}y"].median() / 1e6,
               "median_cap_3y_musd": g[f"cap_avg_{n}y"].median() / 1e6,
               "median_tsr_3y_ann_pct": 100 * g[f"tsr_{n}y_ann"].median(),
               "median_mcap_start_busd": g[f"mcap_start_{n}y"].median() / 1e9}
        if len(g) >= 4:
            rec["spearman_sct_tsr"], rec["spearman_sct_tsr_p"] = stats.spearmanr(g["ln_pay"], g["tsr_pp_w"])
            rec["spearman_cap_tsr"], rec["spearman_cap_tsr_p"] = stats.spearmanr(g["asinh_cap"], g["tsr_pp_w"])
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("median_sct_3y_musd", ascending=False)


def outliers(m: pd.DataFrame, k: int = config.N_OUTLIERS_EACH_SIDE) -> tuple[pd.DataFrame, dict]:
    """Residuals from model A3 (primary window). Positive = paid more than
    predicted given TSR, size and sector ('overpaid vs. performance')."""
    n = config.PRIMARY_WINDOW_YEARS
    d = prepare(m, n)
    res = fit("ln_pay ~ tsr_pp_w + ln_mcap + C(sector)", d)
    d["fitted_ln_pay"] = res.fittedvalues
    d["resid"] = res.resid
    d["predicted_pay"] = np.exp(d["fitted_ln_pay"])
    d["pay_vs_predicted_pct"] = 100 * (np.exp(d["resid"]) - 1)
    infl = res.get_influence()
    d["student_resid"] = infl.resid_studentized_internal
    d["resid_rank"] = d["resid"].rank(ascending=False).astype(int)

    # Stability: residual ranks under alternative specifications
    alt = {}
    for name, f, data in (
        ("no_sector_fe", "ln_pay ~ tsr_pp_w + ln_mcap", d),
        ("cap_model", "asinh_cap ~ tsr_pp_w + ln_mcap + C(sector)", d),
    ):
        r = fit(f, data)
        alt[name] = r.resid.rank(ascending=False)
    d5 = prepare(m, 5)
    r5 = fit("ln_pay ~ tsr_pp_w + ln_mcap + C(sector)", d5)
    alt["window_5y"] = r5.resid.rank(ascending=False)
    for name, ranks in alt.items():
        d[f"rank_{name}"] = ranks.reindex(d.index)
    d["rank_window_5y"] = d["ticker"].map(dict(zip(d5["ticker"], r5.resid.rank(ascending=False))))
    # Model estimated without the four no-equity-grant companies, applied to all
    r7 = fit("ln_pay ~ tsr_pp_w + ln_mcap + C(sector)", d[d["mix_equity"].fillna(0) > 0.05])
    d["rank_excl_no_equity"] = (d["ln_pay"] - r7.predict(d)).rank(ascending=False)

    cols = ["ticker", "company", "sector", "ceo_name_latest", "latest_fy", f"sct_avg_{n}y", "predicted_pay",
            "pay_vs_predicted_pct", "resid", "student_resid", f"tsr_{n}y", f"tsr_{n}y_ann", f"peer_tsr_{n}y",
            f"cap_avg_{n}y", f"mcap_start_{n}y", f"ceo_change_{n}y", "co_ceo", "mix_equity", "mix_option",
            "mix_cash_incentive", "tsr_discrepancy", "resid_rank", "rank_no_sector_fe", "rank_cap_model",
            "rank_window_5y", "rank_excl_no_equity", "proxy_url"]
    ranked = d.sort_values("resid", ascending=False)[cols].reset_index(drop=True)
    ranked.to_csv(config.DATA_PROCESSED / "residuals_3y.csv", index=False)
    over = ranked.head(k)
    under = ranked.tail(k).iloc[::-1]
    # Misalignment screen: residual sign disagrees with relative performance
    med = ranked[f"tsr_{n}y_ann"].median()
    mis_over = ranked[(ranked["resid"] > 0) & (ranked[f"tsr_{n}y_ann"] < med)].head(k)
    mis_under = ranked[(ranked["resid"] < 0) & (ranked[f"tsr_{n}y_ann"] > med)].tail(k).iloc[::-1]
    mis_over.to_csv(OUT_TABLES / "misaligned_high_pay_low_tsr.csv", index=False)
    mis_under.to_csv(OUT_TABLES / "misaligned_low_pay_high_tsr.csv", index=False)
    top_over_tsr_rank = ranked[f"tsr_{n}y_ann"].rank(pct=True)
    summary = {"model": "ln(avg SCT pay, 3y) ~ TSR + ln(mcap at window start) + sector FE",
               "n": int(res.nobs), "r2": float(res.rsquared), "resid_sd": float(np.std(res.resid, ddof=1)),
               "median_tsr_ann": float(med),
               "overpaid_median_tsr_pctile": float(top_over_tsr_rank.head(k).median()),
               "overpaid": over.to_dict(orient="records"), "underpaid": under.to_dict(orient="records"),
               "misaligned_high_pay_low_tsr": mis_over.to_dict(orient="records"),
               "misaligned_low_pay_high_tsr": mis_under.to_dict(orient="records")}
    return ranked, summary


def pay_mix_analysis(m: pd.DataFrame) -> dict:
    n = config.PRIMARY_WINDOW_YEARS
    d = prepare(m, n).dropna(subset=["mix_equity"])
    out = {"n": int(len(d)),
           "median_mix": {c: float(d[f"mix_{c}"].median()) for c in
                          ("salary", "bonus", "stock", "option", "neip", "pension", "other",
                           "equity", "cash_incentive")},
           "mean_mix": {c: float(d[f"mix_{c}"].mean()) for c in
                        ("salary", "bonus", "stock", "option", "neip", "pension", "other",
                         "equity", "cash_incentive")},
           "share_using_options": float(d["uses_options"].mean()),
           "corr": {}}
    for c in ("equity", "option", "stock", "cash_incentive", "salary"):
        out["corr"][c] = corr(d[f"mix_{c}"], d["tsr_pp_w"])
    res = fit("tsr_pp_w ~ I(100*mix_equity) + ln_mcap + C(sector)", d)
    out["tsr_on_equity_share"] = summarize(res, key="I(100 * mix_equity)")
    dg = d[d["mix_equity"] > 0.05]
    out["excl_no_equity_grants"] = {"n": int(len(dg)),
                                    "excluded": sorted(d.loc[d["mix_equity"] <= 0.05, "ticker"].tolist()),
                                    "corr_equity": corr(dg["mix_equity"], dg["tsr_pp_w"]),
                                    "corr_option": corr(dg["mix_option"], dg["tsr_pp_w"]),
                                    "tsr_on_equity_share": summarize(
                                        fit("tsr_pp_w ~ I(100*mix_equity) + ln_mcap + C(sector)", dg),
                                        key="I(100 * mix_equity)")}
    d["tsr_quintile"] = pd.qcut(d["tsr_pp"], 5, labels=["Q1 (lowest)", "Q2", "Q3", "Q4", "Q5 (highest)"])
    q = d.groupby("tsr_quintile", observed=True).agg(
        n=("ticker", "size"), tsr_ann_median=("tsr_pp", "median"),
        salary=("mix_salary", "mean"), cash_incentive=("mix_cash_incentive", "mean"),
        stock=("mix_stock", "mean"), option=("mix_option", "mean"),
        pension_other=("mix_pension", "mean"), other=("mix_other", "mean"),
        sct_median=(f"sct_avg_{n}y", "median"), cap_median=(f"cap_avg_{n}y", "median"))
    q["pension_other"] = q["pension_other"] + q.pop("other")
    q.to_csv(OUT_TABLES / "pay_mix_by_tsr_quintile.csv")
    out["by_quintile"] = q.reset_index().to_dict(orient="records")
    return out


def panel_analysis(panel: pd.DataFrame) -> dict:
    """Within-company: does pay move with the *same year's* TSR?"""
    p = panel.dropna(subset=["indep_tsr_annual", "ceo_sct_total", "ceo_cap"]).copy()
    p = p[p["ceo_sct_total"] > 0]  # log pay needs a positive figure ($0 years: Tesla 2021-23)
    p["tsr_pp"] = winsorize(100 * p["indep_tsr_annual"])
    p["ln_sct"] = np.log(p["ceo_sct_total"])
    p["asinh_cap"] = np.arcsinh(p["ceo_cap"] / 1e6)
    p = p.sort_values(["ticker", "fy"])
    p["tsr_pp_lag"] = p.groupby("ticker")["tsr_pp"].shift(1)
    out = {"n": int(len(p)), "n_companies": int(p["ticker"].nunique())}
    specs = {
        "sct_same_year": "ln_sct ~ tsr_pp + C(ticker) + C(fy)",
        "sct_prior_year": "ln_sct ~ tsr_pp_lag + C(ticker) + C(fy)",
        "cap_same_year": "asinh_cap ~ tsr_pp + C(ticker) + C(fy)",
    }
    for name, f in specs.items():
        data = p.dropna(subset=["tsr_pp_lag"]) if "lag" in f else p
        res = smf.ols(f, data=data).fit(cov_type="cluster", cov_kwds={"groups": data["ticker"]})
        key = "tsr_pp_lag" if "lag" in f else "tsr_pp"
        out[name] = {"n": int(res.nobs), "coef": float(res.params[key]), "se": float(res.bse[key]),
                     "p": float(res.pvalues[key]), "r2_within_approx": float(res.rsquared),
                     "pct_pay_per_10pp_tsr": float(100 * (np.exp(10 * res.params[key]) - 1))}
    out["corr_cap_tsr_pooled"] = corr(p["asinh_cap"], p["tsr_pp"])
    out["corr_sct_tsr_pooled"] = corr(p["ln_sct"], p["tsr_pp"])
    return out


def say_on_pay_analysis(m: pd.DataFrame) -> dict:
    """Do shareholders vote against CEOs paid above the model?"""
    path = config.DATA_PROCESSED / "say_on_pay.csv"
    if not path.exists():
        return {}
    sop = pd.read_csv(path)
    agg = sop.groupby("ticker").agg(sop_avg=("support", "mean"), sop_min=("support", "min"),
                                    sop_meetings=("support", "size"))
    latest = sop.sort_values("meeting_date").groupby("ticker").tail(1).set_index("ticker")["support"]
    agg["sop_latest"] = latest
    res = pd.read_csv(config.DATA_PROCESSED / "residuals_3y.csv")[["ticker", "resid", "tsr_3y_ann"]]
    d = res.merge(agg, left_on="ticker", right_index=True, how="inner")
    d.to_csv(OUT_TABLES / "say_on_pay_vs_residual.csv", index=False)
    d["resid_q"] = pd.qcut(d["resid"], 4, labels=["Q1 (most underpaid)", "Q2", "Q3", "Q4 (most overpaid)"])
    by_q = d.groupby("resid_q", observed=True)["sop_avg"].agg(["mean", "median", "size"]).reset_index()
    fit_res = fit("I(100*sop_avg) ~ resid + I(100*tsr_3y_ann)", d)
    return {
        "n_companies": int(len(d)), "n_meetings": int(len(sop)),
        "median_support": float(sop["support"].median()),
        "n_failed_votes": int((sop["support"] < 0.5).sum()),
        "failed_votes": sop.loc[sop["support"] < 0.5, ["ticker", "meeting_date", "support"]].to_dict(orient="records"),
        "n_below_70": int((sop["support"] < 0.7).sum()),
        "companies_below_70": sorted(sop.loc[sop["support"] < 0.7, "ticker"].unique().tolist()),
        "corr_resid_support": corr(d["resid"], d["sop_avg"]),
        "corr_tsr_support": corr(d["tsr_3y_ann"], d["sop_avg"]),
        "ols_support_on_resid_tsr": summarize(fit_res, key="resid"),
        "support_by_resid_quartile": by_q.to_dict(orient="records"),
    }


def tsr_quality(m: pd.DataFrame) -> dict:
    P = config.DATA_PROCESSED
    fis = pd.read_csv(P / "tsr_fiscal.csv")
    xc = pd.read_csv(P / "tsr_crosscheck.csv")
    chk = pd.read_csv(P / "tsr_adjclose_check.csv")
    reasons = fis.dropna(subset=["discrepancy_reason"]).groupby("ticker")["discrepancy_reason"] \
        .agg(lambda s: "stale_base" if (s == "stale_base").all() else
             ("misdated" if (s == "misdated").all() else "mixed/other"))
    # silent stale base: earlier years match old base better than new base
    f = fis.copy()
    f["is_latest"] = f.groupby("ticker")["fy"].transform("max") == f["fy"]
    early = f[~f["is_latest"]].dropna(subset=["proxy_tsr_value"])
    early = early.assign(gap_new=(early["indep_tsr_value"] - early["proxy_tsr_value"]).abs(),
                         gap_old=(early["alt_base_value"] - early["proxy_tsr_value"]).abs())
    stale_any = early.groupby("ticker").apply(
        lambda g: bool(((g["gap_old"] < 1.0) & (g["gap_new"] > 2.0)).mean() > 0.5), include_groups=False)
    return {
        "n_company_years_compared": int(fis["proxy_tsr_value"].notna().sum()),
        "median_abs_gap_pts": float(fis["diff_pts"].abs().median()),
        "share_within_1pt": float((fis["diff_pts"].abs() <= 1).mean()),
        "share_within_1pt_latest_year": float((f[f["is_latest"]]["diff_pts"].abs() <= 1).mean()),
        "n_companies_flagged": int(xc["tsr_discrepancy"].sum()),
        "flagged_tickers": sorted(xc.loc[xc["tsr_discrepancy"], "ticker"].tolist()),
        "flag_reasons": reasons.value_counts().to_dict(),
        "n_companies_stale_base_any_size": int(stale_any.sum()),
        "stale_base_tickers": sorted(stale_any[stale_any].index.tolist()),
        "tri_vs_adjclose_median_abs_diff_5y": float(chk["diff"].abs().median()),
    }


def run() -> dict:
    P = config.DATA_PROCESSED
    m = pd.read_csv(P / "master.csv")
    panel = pd.read_csv(P / "master_panel.csv")
    results = {"config": {"primary_window_years": config.PRIMARY_WINDOW_YEARS, "winsor": WINSOR,
                          "scope": config.scope_label(), "as_of": config.AS_OF_DATE}}
    results["descriptives"] = descriptives(m, panel)
    results["correlations"] = correlations(m)
    reg, reg_table = regressions(m)
    results["regressions"] = reg
    reg_table.to_csv(OUT_TABLES / "regression_summary.csv", index=False)
    sec = sector_analysis(m)
    sec.to_csv(OUT_TABLES / "sector_summary.csv", index=False)
    results["sectors"] = sec.to_dict(orient="records")
    ranked, outl = outliers(m)
    results["outliers"] = outl
    ranked.head(config.N_OUTLIERS_EACH_SIDE).to_csv(OUT_TABLES / "outliers_overpaid.csv", index=False)
    ranked.tail(config.N_OUTLIERS_EACH_SIDE).iloc[::-1].to_csv(OUT_TABLES / "outliers_underpaid.csv", index=False)
    results["pay_mix"] = pay_mix_analysis(m)
    results["panel"] = panel_analysis(panel)
    results["tsr_quality"] = tsr_quality(m)
    results["say_on_pay"] = say_on_pay_analysis(m)

    path = config.OUTPUT / "results.json"
    # Keep sections written by later pipeline steps (e.g. the strategy test),
    # so re-running the analysis alone (as the notebook does) never drops them.
    if path.exists():
        old = json.loads(path.read_text())
        for k, v in old.items():
            results.setdefault(k, v)
    path.write_text(json.dumps(results, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    _print_headline(results)
    return results


def _print_headline(r: dict) -> None:
    reg = r["regressions"]
    for key in ("sct_3y_1_simple", "sct_3y_2_size", "sct_3y_3_size_sector",
                "cap_3y_1_simple", "cap_3y_2_size", "cap_3y_3_size_sector"):
        c = reg[key]["coefs"]["tsr_pp_w"]
        print(f"[analysis] {key:24s} n={reg[key]['n']:3d} b_tsr={c['coef']:+.4f} (p={c['p']:.3f}) "
              f"R2={reg[key]['r2']:.3f}  size={reg[key].get('size_elasticity', float('nan')):.3f}")
    print("[analysis] overpaid:", [(o["ticker"], round(o["pay_vs_predicted_pct"])) for o in r["outliers"]["overpaid"]])
    print("[analysis] underpaid:", [(o["ticker"], round(o["pay_vs_predicted_pct"])) for o in r["outliers"]["underpaid"]])


if __name__ == "__main__":
    run()
