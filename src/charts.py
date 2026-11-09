"""Phase 6a - Publication charts (static PNG for the report and README).

Design rules (validated palette, see ASSUMPTIONS.md / dataviz method):
* Diverging poles for polarity: red = paid above model ("overpaid"),
  blue = paid below model ("underpaid"); context points in neutral gray.
* Pay-mix stack uses categorical slots 1-5 in fixed order; segments are
  separated by 2px surface gaps and directly labelled (three slots are below
  3:1 contrast, so labels + the CSV table view provide relief).
* One y-axis per plot, hairline solid grid, text in ink tokens (never series
  colour), selective direct labels.
Every number drawn comes from ``output/results.json`` or ``data/processed``.
"""
from __future__ import annotations

import json
import logging

import matplotlib
import matplotlib.dates

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from adjustText import adjust_text  # noqa: E402
from scipy import stats  # noqa: E402

from . import config  # noqa: E402

# ---------------------------------------------------------------------------
# Tokens (reference palette, light surface)
# ---------------------------------------------------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
CONTEXT = "#b9b8b2"           # neutral context points
BLUE = "#2a78d6"              # slot 1 / diverging cool pole
RED = "#e34948"               # diverging warm pole
ORANGE = "#eb6834"            # slot 2
CATS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]  # slots 1-5
CAT_TEXT = ["#ffffff", "#ffffff", "#ffffff", "#0b0b0b", "#ffffff"]

SOURCE = ("Source: SEC EDGAR DEF 14A pay-versus-performance XBRL (ecd taxonomy) and Summary "
          "Compensation Tables; Yahoo Finance prices. 100-company sector-stratified S&P 500 sample.")


def _fonts() -> list[str]:
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    return [f for f in ("Inter", "Helvetica Neue", "Arial", "DejaVu Sans") if f in have] or ["sans-serif"]


def _style() -> None:
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)  # glyph-fallback weight notices
    plt.rcParams.update({
        "font.family": _fonts(),
        "font.size": 10.5,
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
        "axes.labelcolor": INK_2, "axes.labelsize": 10.5,
        "axes.titlesize": 12, "axes.titleweight": "semibold", "axes.titlecolor": INK,
        "axes.titlelocation": "left", "axes.titlepad": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.7, "grid.linestyle": "-",
        "axes.axisbelow": True,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 9.5, "ytick.labelsize": 9.5,
        "xtick.major.size": 0, "ytick.major.size": 0,
        "legend.frameon": False, "legend.fontsize": 9.5, "legend.labelcolor": INK_2,
        "text.color": INK,
    })


def _load():
    P = config.DATA_PROCESSED
    r = json.loads((config.OUTPUT / "results.json").read_text())
    m = pd.read_csv(P / "master.csv")
    res = pd.read_csv(P / "residuals_3y.csv")
    return r, m, res


def _save(fig, name: str, dpi: int = 200) -> None:
    path = config.CHARTS / name
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"[charts] {path.relative_to(config.ROOT)}")


def _footer(fig, text: str = SOURCE, y: float = -0.02) -> None:
    fig.text(0.01, y, text, ha="left", va="top", fontsize=8, color=MUTED, wrap=True)


def _pfmt(p: float) -> str:
    if p < 0.001:
        return "p < 0.001"
    return f"p = {p:.3f}" if p < 0.01 else f"p = {p:.2f}"


def _money_axis(ax, axis="y"):
    def f(v, _):
        sign = "\u2212" if v < 0 else ""
        a = abs(v)
        return f"{sign}${a:,.0f}M" if a >= 1 or a == 0 else f"{sign}${a:,.1f}M"
    fmt = mticker.FuncFormatter(f)
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


# ---------------------------------------------------------------------------
# 1. Pay vs TSR scatter (granted vs realized, small multiples)
# ---------------------------------------------------------------------------
def pay_vs_tsr(r, m, res) -> None:
    n = config.PRIMARY_WINDOW_YEARS
    d = res.copy()
    d["tsr"] = 100 * d[f"tsr_{n}y_ann"]
    d["sct_m"] = d[f"sct_avg_{n}y"] / 1e6
    d["cap_m"] = d[f"cap_avg_{n}y"] / 1e6
    over = {o["ticker"] for o in r["outliers"]["overpaid"]}
    under = {o["ticker"] for o in r["outliers"]["underpaid"]}
    lo, hi = r["descriptives"]["winsor_bounds_3y_pp"]
    xmax = 100.0

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), sharex=True)
    panels = [("sct_m", "sct_3y_1_simple", "Granted pay (Summary Compensation Table)", "log"),
              ("cap_m", "cap_3y_1_simple", "Compensation actually paid (CAP)", "symlog")]
    for ax, (col, model, title, scale) in zip(axes, panels):
        reg = r["regressions"][model]
        c = reg["coefs"]["tsr_pp_w"]
        ctx = d[~d["ticker"].isin(over | under)]
        x_plot = d["tsr"].clip(upper=xmax)
        ax.scatter(ctx["tsr"].clip(upper=xmax), ctx[col], s=34, color=CONTEXT, edgecolor=SURFACE,
                   linewidth=1.2, zorder=2, label="Other sample companies")
        for grp, color, lab in ((over, RED, "Paid most above model (top 5)"),
                                (under, BLUE, "Paid most below model (bottom 5)")):
            g = d[d["ticker"].isin(grp)]
            ax.scatter(g["tsr"].clip(upper=xmax), g[col], s=58, color=color, edgecolor=SURFACE,
                       linewidth=1.5, zorder=3, label=lab)
        # fitted line from the simple model (TSR winsorised to [lo, hi])
        xs = np.linspace(lo, hi, 50)
        b0 = reg["coefs"]["Intercept"]["coef"]
        # ln_pay is in ln($); asinh_cap is asinh($M)
        ys = np.exp(b0 + c["coef"] * xs) / 1e6 if scale == "log" else np.sinh(b0 + c["coef"] * xs)
        ax.plot(xs, ys, color=INK_2, linewidth=2, zorder=4, label="OLS fit (simple model)")
        ax.set_yscale(scale, **({"linthresh": 10} if scale == "symlog" else {}))
        ax.set_title(title, pad=24)
        ax.text(0.0, 1.015, f"R² = {100 * reg['r2']:.1f}%   ·   +10 pp TSR ≈ {reg['pct_pay_per_10pp_tsr']:+.0f}% pay   ·   "
                          f"{_pfmt(c['p'])}", transform=ax.transAxes, fontsize=9.5, color=INK_2, va="bottom")
        ax.set_xlabel(f"Annualised TSR over the same {n} fiscal years (%)")
        ax.set_xlim(-55, xmax + 6)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:+.0f}%" if v else "0%"))
        texts = []
        for _, row in d[d["ticker"].isin(over | under)].iterrows():
            lbl = row["ticker"] + (f" ({row['tsr']:+.0f}%/yr ▸)" if row["tsr"] > xmax else "")
            texts.append(ax.text(min(row["tsr"], xmax), row[col], lbl, fontsize=8.8, color=INK, zorder=5))
        adjust_text(texts, ax=ax, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.6),
                    expand=(1.3, 1.6))
    axes[0].set_ylabel(f"CEO pay, {n}-year average ($M, log scale)")
    axes[1].set_ylabel(f"CEO pay, {n}-year average ($M, symmetric log)")
    for ax in axes:
        _money_axis(ax)
    axes[1].yaxis.set_major_locator(mticker.FixedLocator([-100, -10, 0, 10, 100, 1000, 10000]))
    axes[0].yaxis.set_major_locator(mticker.FixedLocator([1, 2, 5, 10, 20, 50, 100]))
    axes[0].yaxis.set_minor_locator(mticker.NullLocator())
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.08))
    fig.suptitle("Granted CEO pay barely moves with shareholder returns; realised pay moves a lot",
                 x=0.01, ha="left", fontsize=15, fontweight="semibold", y=1.05)
    fig.text(0.01, 0.985, f"{r['outliers']['n']} S&P 500 companies, average annual CEO pay vs annualised TSR, "
                          f"latest {n} fiscal years. TSR right-clipped at +{xmax:.0f}% for display.",
             ha="left", fontsize=10, color=INK_2)
    _footer(fig, SOURCE, y=-0.1)
    _save(fig, "01_pay_vs_tsr_scatter.png")


# ---------------------------------------------------------------------------
# 2. Sector breakdown (small multiples)
# ---------------------------------------------------------------------------
def sector_breakdown(r) -> None:
    s = pd.DataFrame(r["sectors"]).sort_values("median_sct_3y_musd")
    labels = [f"{sec}  (n={n})" for sec, n in zip(s["sector"], s["n"])]
    y = np.arange(len(s))
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.4), sharey=True,
                             gridspec_kw={"width_ratios": [1, 1, 1.25], "wspace": 0.08})
    ax = axes[0]
    ax.barh(y, s["median_sct_3y_musd"], height=0.62, color=BLUE, edgecolor=SURFACE, linewidth=2)
    for yi, v in zip(y, s["median_sct_3y_musd"]):
        ax.text(v + 0.4, yi, f"${v:.1f}M", va="center", fontsize=9, color=INK_2)
    ax.set_title("Median granted pay, 3-yr avg")
    ax.set_xlim(0, s["median_sct_3y_musd"].max() * 1.25)
    _money_axis(ax, "x")
    ax.set_yticks(y, labels)
    ax.tick_params(axis="y", colors=INK_2, labelsize=10)
    ax.grid(axis="y", visible=False)

    ax = axes[1]
    ax.barh(y, s["median_tsr_3y_ann_pct"], height=0.62, color=BLUE, edgecolor=SURFACE, linewidth=2)
    for yi, v in zip(y, s["median_tsr_3y_ann_pct"]):
        ax.text(v + (1 if v >= 0 else -1), yi, f"{v:+.0f}%", va="center",
                ha="left" if v >= 0 else "right", fontsize=9, color=INK_2)
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_title("Median TSR, %/yr (3 yrs)")
    ax.set_xlim(min(-5, s["median_tsr_3y_ann_pct"].min() * 1.6), s["median_tsr_3y_ann_pct"].max() * 1.35)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:+.0f}%" if v else "0%"))
    ax.grid(axis="y", visible=False)

    ax = axes[2]
    ax.axvline(0, color=AXIS, lw=1)
    for yi, a, b in zip(y, s["spearman_sct_tsr"], s["spearman_cap_tsr"]):
        ax.plot([a, b], [yi, yi], color=GRID, lw=2, zorder=1)
    same = np.isclose(s["spearman_sct_tsr"].to_numpy(), s["spearman_cap_tsr"].to_numpy(), atol=0.02)
    off = np.where(same, 0.13, 0.0)  # nudge coincident dots vertically so both stay visible
    ax.scatter(s["spearman_sct_tsr"], y + off, s=70, color=BLUE, edgecolor=SURFACE, lw=1.5, zorder=3,
               label="Granted pay (SCT) vs TSR")
    ax.scatter(s["spearman_cap_tsr"], y - off, s=70, color=ORANGE, edgecolor=SURFACE, lw=1.5, zorder=3,
               label="Pay actually paid (CAP) vs TSR")
    ax.set_xlim(-1.05, 1.05)
    ax.set_title("Rank correlation with TSR (Spearman ρ)")
    ax.legend(loc="lower center", bbox_to_anchor=(0.45, -0.25), ncol=1)
    ax.grid(axis="y", visible=False)
    n_cap = int((s["spearman_cap_tsr"] > 0.3).sum())
    n_sct = int((s["spearman_sct_tsr"] > 0.3).sum())
    fig.suptitle(f"By sector: realised pay tracks returns in {n_cap} of {len(s)} sectors; granted pay in only {n_sct}",
                 x=0.01, ha="left", fontsize=15, fontweight="semibold", y=1.04)
    fig.text(0.01, 0.975, "Sectors sorted by median granted pay. 'Tracks' = Spearman ρ > 0.3. Small sector samples "
                          "(n = 4-17) make sector correlations indicative only; overlapping dots mean equal ρ.",
             fontsize=10, color=INK_2, ha="left")
    _footer(fig, SOURCE, y=-0.08)
    _save(fig, "02_sector_breakdown.png")


# ---------------------------------------------------------------------------
# 3. Residuals: ranked outliers + diagnostics
# ---------------------------------------------------------------------------
def residuals(r, res) -> None:
    k = 10
    top = res.head(k)
    bot = res.tail(k)
    d = pd.concat([top, bot]).iloc[::-1].reset_index(drop=True)
    y = np.arange(len(d))
    colors = [RED if v > 0 else BLUE for v in d["resid"]]
    fig, ax = plt.subplots(figsize=(10.5, 7.6))
    ax.barh(y, d["resid"], height=0.66, color=colors, edgecolor=SURFACE, linewidth=2)
    ax.axvline(0, color=AXIS, lw=1)
    for yi, rv, pct, tsr in zip(y, d["resid"], d["pay_vs_predicted_pct"], d["tsr_3y_ann"]):
        ax.text(rv + (0.04 if rv > 0 else -0.04), yi, f"{pct:+.0f}%  ·  TSR {100 * tsr:+.0f}%/yr",
                va="center", ha="left" if rv > 0 else "right", fontsize=8.8, color=INK_2)
    names = [f"{t}  {c[:24]}" for t, c in zip(d["ticker"], d["company"])]
    ax.set_yticks(y, names)
    ax.tick_params(axis="y", colors=INK, labelsize=9.5)
    ax.grid(axis="y", visible=False)
    ax.axhline(k - 0.5, color=GRID, lw=1)
    ticks = np.log(np.array([0.1, 0.25, 0.5, 1, 2, 4]))
    ax.set_xticks(ticks, ["-90%", "-75%", "-50%", "0", "+100%", "+300%"])
    ax.set_xlim(np.log(0.012), np.log(9))
    ax.set_xlabel("Actual 3-yr average granted pay vs model prediction (log scale)")
    ax.set_title(f"Ten highest and ten lowest residuals (model R² = {100 * r['outliers']['r2']:.0f}%, "
                 f"n = {r['outliers']['n']})")
    fig.suptitle("Who is paid most above and below what size, sector and TSR predict",
                 x=0.01, ha="left", fontsize=15, fontweight="semibold", y=1.0)
    _footer(fig, "Model: ln(avg SCT pay) ~ annualised TSR + ln(market cap at window start) + GICS sector, "
                 "OLS with HC3 errors. Red = paid above model, blue = below.\n" + SOURCE, y=-0.02)
    _save(fig, "03_residual_outliers.png")

    # diagnostics
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    ax = axes[0]
    fitted = res["predicted_pay"]
    ax.scatter(np.log(fitted / 1e6), res["resid"], s=30, color=BLUE, edgecolor=SURFACE, lw=1)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xlabel("Fitted ln(pay, $M)")
    ax.set_ylabel("Residual (log points)")
    ax.set_title("Residuals vs fitted")
    ax = axes[1]
    (osm, osr), (slope, inter, _) = stats.probplot(res["student_resid"], dist="norm")
    ax.scatter(osm, osr, s=26, color=BLUE, edgecolor=SURFACE, lw=1)
    ax.plot(osm, slope * np.array(osm) + inter, color=INK_2, lw=1.6)
    ax.set_xlabel("Theoretical normal quantiles")
    ax.set_ylabel("Studentised residual")
    ax.set_title("Normal Q-Q")
    fig.suptitle("Primary model diagnostics", x=0.01, ha="left", fontsize=13, fontweight="semibold", y=1.02)
    _save(fig, "03b_residual_diagnostics.png")


# ---------------------------------------------------------------------------
# 4. Pay mix by TSR quintile (100% stacked bars)
# ---------------------------------------------------------------------------
def pay_mix(r) -> None:
    q = pd.DataFrame(r["pay_mix"]["by_quintile"])
    comps = [("salary", "Salary"), ("cash_incentive", "Cash bonus & incentive"), ("stock", "Stock awards"),
             ("option", "Option awards"), ("pension_other", "Pension & other")]
    q = q.iloc[::-1].reset_index(drop=True)
    y = np.arange(len(q))
    fig, ax = plt.subplots(figsize=(11, 4.6))
    left = np.zeros(len(q))
    for (col, lab), color, tcol in zip(comps, CATS, CAT_TEXT):
        vals = 100 * q[col].to_numpy()
        ax.barh(y, vals, left=left, height=0.64, color=color, edgecolor=SURFACE, linewidth=2, label=lab)
        for yi, l0, v in zip(y, left, vals):
            if v >= 6:
                ax.text(l0 + v / 2, yi, f"{v:.0f}%", ha="center", va="center", fontsize=9, color=tcol)
        left += vals
    ylabels = [f"{a}\nmedian TSR {b:+.0f}%/yr · n={c}" for a, b, c in
               zip(q["tsr_quintile"], q["tsr_ann_median"], q["n"])]
    ax.set_yticks(y, ylabels)
    ax.tick_params(axis="y", colors=INK_2, labelsize=9.5)
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter())
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.32), ncol=5)
    mx = r["pay_mix"]
    eq = mx["corr"]["equity"]
    eqx = mx["excl_no_equity_grants"]["corr_equity"]
    excl = mx["excl_no_equity_grants"]["excluded"]
    fig.suptitle("Equity-heavy pay is not associated with higher returns",
                 x=0.01, ha="left", fontsize=15, fontweight="semibold", y=1.1)
    fig.text(0.01, 1.03, f"Average share of 3-year granted pay by component, companies grouped by 3-yr TSR quintile. "
                         f"Equity share vs TSR: Spearman ρ = {eq['spearman_rho']:.2f} ({_pfmt(eq['spearman_p'])}); "
                         f"excluding the {len(excl)} no-new-grant CEOs ({', '.join(excl)}) ρ = {eqx['spearman_rho']:.2f}.\n"
                         f"The top quintile's large 'pension & other' share comes from those founder-led companies, where "
                         f"reported pay is mostly security and perquisites.", fontsize=9.5, color=INK_2, ha="left",
             va="top")
    _footer(fig, SOURCE, y=-0.16)
    _save(fig, "04_pay_mix_by_tsr_quintile.png")


# ---------------------------------------------------------------------------
# 5. Say-on-pay vs residual
# ---------------------------------------------------------------------------
def say_on_pay(r) -> None:
    path = config.OUTPUT / "tables" / "say_on_pay_vs_residual.csv"
    if not path.exists():
        return
    d = pd.read_csv(path)
    s = r["say_on_pay"]
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    ax.axhline(70, color=AXIS, lw=1)
    ax.text(ax.get_xlim()[0] if False else d["resid"].min() - 0.05, 70.8, "70%: proxy-adviser responsiveness threshold",
            fontsize=8.5, color=MUTED, ha="left")
    ax.scatter(d["resid"], 100 * d["sop_avg"], s=40, color=BLUE, edgecolor=SURFACE, lw=1.3, zorder=3)
    texts = [ax.text(rr, 100 * sv, t, fontsize=8.8, color=INK)
             for t, rr, sv in zip(d["ticker"], d["resid"], d["sop_avg"]) if sv < 0.75]
    adjust_text(texts, ax=ax, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.6))
    ax.set_xlabel("Pay vs model (residual, log points): left = underpaid, right = overpaid")
    ax.set_ylabel("Average say-on-pay support, 2024-26 (%)")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    c = s["corr_resid_support"]
    ax.set_title(f"Spearman ρ = {c['spearman_rho']:.2f} ({_pfmt(c['spearman_p'])}), n = {s['n_companies']} companies, "
                 f"{s['n_meetings']} meetings")
    fig.suptitle("Shareholders push back modestly on above-model pay", x=0.01, ha="left",
                 fontsize=15, fontweight="semibold", y=1.02)
    _footer(fig, "Say-on-pay = For / (For + Against + Abstain) from 8-K Item 5.07 filings. Labelled: average support "
                 "below 75%.\n" + SOURCE, y=-0.04)
    _save(fig, "05_say_on_pay_vs_residual.png")


# ---------------------------------------------------------------------------
# 6. TSR cross-check
# ---------------------------------------------------------------------------
def tsr_crosscheck(r) -> None:
    f = pd.read_csv(config.DATA_PROCESSED / "tsr_fiscal.csv").dropna(subset=["proxy_tsr_value", "indep_tsr_value"])
    fig, ax = plt.subplots(figsize=(7.4, 6.4))
    lim = [min(f["proxy_tsr_value"].min(), f["indep_tsr_value"].min()) * 0.85,
           max(f["proxy_tsr_value"].max(), f["indep_tsr_value"].max()) * 1.15]
    ax.plot(lim, lim, color=AXIS, lw=1.2, zorder=1)
    ok = f[~f["discrepancy_flag"]]
    bad = f[f["discrepancy_flag"]]
    ax.scatter(ok["indep_tsr_value"], ok["proxy_tsr_value"], s=22, color=CONTEXT, edgecolor=SURFACE, lw=0.8,
               label=f"Within {config.TSR_DISCREPANCY_PP:.0f} pts ({len(ok)} company-years)", zorder=2)
    ax.scatter(bad["indep_tsr_value"], bad["proxy_tsr_value"], s=34, color=RED, edgecolor=SURFACE, lw=1,
               label=f"Gap > {config.TSR_DISCREPANCY_PP:.0f} pts ({len(bad)} company-years, "
                     f"{bad['ticker'].nunique()} companies)", zorder=3)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(lim); ax.set_ylim(lim)
    for a in (ax.xaxis, ax.yaxis):
        a.set_major_locator(mticker.FixedLocator([25, 50, 100, 200, 400, 800]))
        a.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
        a.set_minor_formatter(mticker.NullFormatter())
    ax.set_xlabel("Independent: value of $100 (our total-return index)")
    ax.set_ylabel("Company-reported in proxy: value of $100")
    q = r["tsr_quality"]
    ax.set_title(f"Median gap {q['median_abs_gap_pts']:.2f} pts; {100 * q['share_within_1pt']:.0f}% of company-years "
                 f"within 1 pt", fontsize=10.5)
    ax.legend(loc="upper left")
    fig.suptitle("Proxy TSR cross-check: mostly exact, with a cluster of filing errors", x=0.01, ha="left",
                 fontsize=14, fontweight="semibold", y=1.01)
    reasons = q["flag_reasons"]
    _footer(fig, "Flagged companies by diagnosis: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in reasons.items()) +
            ".\n'Stale base' = earlier years not rebased when the PvP table rolled forward; 'misdated' = values tagged "
            "one year early.", y=-0.01)
    _save(fig, "06_tsr_crosscheck.png")


# ---------------------------------------------------------------------------
# 7. LinkedIn summary (4:5 portrait, 1080 x 1350 px)
# ---------------------------------------------------------------------------
def linkedin(r, res) -> None:
    n = config.PRIMARY_WINDOW_YEARS
    d = res.copy()
    d["tsr"] = (100 * d[f"tsr_{n}y_ann"]).clip(upper=100)
    sct = r["regressions"]["sct_3y_1_simple"]
    cap = r["regressions"]["cap_3y_1_simple"]
    size = r["regressions"]["sct_3y_2_size"]
    fig = plt.figure(figsize=(7.2, 9.0), dpi=150)
    fig.text(0.06, 0.955, "Do S&P 500 CEOs get paid", fontsize=22, fontweight="bold", color=INK)
    fig.text(0.06, 0.918, "for shareholder returns?", fontsize=22, fontweight="bold", color=INK)
    fig.text(0.06, 0.885, f"{r['outliers']['n']} companies · SEC pay-versus-performance filings · "
                          f"latest {n} fiscal years", fontsize=10.5, color=INK_2)

    def tile(x, value, line1, line2, color):
        fig.patches.append(matplotlib.patches.FancyBboxPatch((x, 0.735), 0.41, 0.125, transform=fig.transFigure,
                           boxstyle="round,pad=0.004,rounding_size=0.012", facecolor="#f3f2ee", edgecolor="none"))
        fig.patches.append(matplotlib.patches.Rectangle((x + 0.02, 0.835), 0.05, 0.007, transform=fig.transFigure,
                           facecolor=color, edgecolor="none"))
        fig.text(x + 0.02, 0.783, value, fontsize=28, fontweight="bold", color=INK)
        fig.text(x + 0.02, 0.759, line1, fontsize=9.2, color=INK_2)
        fig.text(x + 0.02, 0.744, line2, fontsize=9.2, color=INK_2)

    tile(0.06, f"{100 * sct['r2']:.1f}%", "of the variation in GRANTED pay", f"is explained by {n}-yr TSR", RED)
    tile(0.53, f"{100 * cap['r2']:.0f}%", "of the variation in REALISED pay", f"(comp. actually paid) by TSR", BLUE)

    axes = [fig.add_axes([0.11, 0.40, 0.36, 0.27]), fig.add_axes([0.6, 0.40, 0.36, 0.27])]
    for ax, col, scale, title, color, reg in (
            (axes[0], f"sct_avg_{n}y", "log", "Granted pay", RED, sct),
            (axes[1], f"cap_avg_{n}y", "symlog", "Realised pay", BLUE, cap)):
        yv = d[col] / 1e6
        ax.scatter(d["tsr"], yv, s=16, color=color, alpha=0.85, edgecolor=SURFACE, lw=0.6)
        lo, hi = r["descriptives"]["winsor_bounds_3y_pp"]
        xs = np.linspace(lo, hi, 40)
        b0, b1 = reg["coefs"]["Intercept"]["coef"], reg["coefs"]["tsr_pp_w"]["coef"]
        ax.plot(xs, np.exp(b0 + b1 * xs) / 1e6 if scale == "log" else np.sinh(b0 + b1 * xs), color=INK, lw=2)
        ax.set_yscale(scale, **({"linthresh": 10} if scale == "symlog" else {}))
        ax.set_title(title, fontsize=11.5)
        ax.set_xlabel(f"Annualised TSR, %", fontsize=9)
        ax.tick_params(labelsize=8.5)
        _money_axis(ax)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:+.0f}" if v else "0"))
        if scale == "symlog":
            ax.yaxis.set_major_locator(mticker.FixedLocator([-10, 0, 10, 100, 1000]))
        else:
            ax.yaxis.set_major_locator(mticker.FixedLocator([2, 5, 10, 20, 50]))
            ax.yaxis.set_minor_locator(mticker.NullLocator())
    axes[0].set_ylabel("$M per year, log", fontsize=9)

    ov = r["outliers"]["overpaid"][0]
    un = r["outliers"]["underpaid"][0]
    sop = r["say_on_pay"]["corr_resid_support"]
    cs = r["correlations"][f"{n}y"]
    bullets = [
        f"Size matters more than returns: granted pay ranks track company\n"
        f"size (ρ = {cs['sct_vs_mcap']['spearman_rho']:.2f}) far more than TSR (ρ = {cs['sct_vs_tsr']['spearman_rho']:.2f}, not significant).",
        "Stock prices do the aligning: realised pay rises and falls\nwith returns.",
        f"Biggest outliers: {ov['ticker']} paid {ov['pay_vs_predicted_pct']:+.0f}% vs model; "
        f"{un['ticker']} {un['pay_vs_predicted_pct']:+.0f}%\n(no new CEO equity grant since 2021).",
        f"Shareholders notice: above-model pay gets lower\nsay-on-pay support (Spearman ρ = {sop['spearman_rho']:.2f}).",
    ]
    yb = 0.318
    for b in bullets:
        fig.patches.append(matplotlib.patches.Circle((0.068, yb + 0.0065), 0.0045, transform=fig.transFigure,
                                                     facecolor=INK_2, edgecolor="none"))
        fig.text(0.085, yb + 0.013, b, fontsize=10.2, color=INK, va="top", linespacing=1.45)
        yb -= 0.068
    fig.text(0.06, 0.035, "Data: SEC EDGAR DEF 14A XBRL & Summary Compensation Tables, 8-K vote results, Yahoo Finance.\n"
                          "Analysis: Tyler Quezada. Sector-stratified 100-company sample; correlation, not causation.",
             fontsize=7.8, color=MUTED)
    fig.savefig(config.CHARTS / "linkedin_summary.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)
    print(f"[charts] {(config.CHARTS / 'linkedin_summary.png').relative_to(config.ROOT)}")

# ---------------------------------------------------------------------------
# 8. Strategy test: does excess pay predict future returns?
# ---------------------------------------------------------------------------
def strategy(r) -> None:
    st = r.get("strategy")
    if not st:
        return
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.0), sharey=True)
    for ax, (name, c) in zip(axes, st["cohorts"].items()):
        m = c["measures"]["capm_abnormal"]
        qs = list(m["quintile_median"].keys())
        med = [100 * m["quintile_median"][q] for q in qs]
        wmean = [100 * m["quintile_mean_winsor"][q] for q in qs]
        x = np.arange(len(qs))
        ax.bar(x, med, width=0.6, color=BLUE, edgecolor=SURFACE, linewidth=2, label="Median", zorder=2)
        ax.scatter(x, wmean, s=60, color=ORANGE, edgecolor=SURFACE, lw=1.5, zorder=3,
                   label="Mean (winsorised 5/95%)")
        ax.axhline(0, color=AXIS, lw=1)
        ax.set_xticks(x, [q.replace(" most ", "\nmost ") for q in qs])
        ax.tick_params(axis="x", colors=INK_2, labelsize=9)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:+.0f}pp" if v else "0"))
        ax.grid(axis="x", visible=False)
        ic = m["rank_ic"]
        ax.set_title(f"Cohort {name}: pay {c['pay_window']}, formed {c['formation']}, held {c['years_held']:.1f} yrs",
                     pad=22)
        ax.text(0, 1.015, f"n = {c['n']}  ·  rank IC = {ic['spearman_rho']:+.2f} ({_pfmt(ic['spearman_p'])})  ·  "
                          f"Q5−Q1 median {100 * m['q5_minus_q1_median']:+.1f}pp ({_pfmt(m['mannwhitney_p'])})",
                transform=ax.transAxes, fontsize=9.5, color=INK_2, va="bottom")
    axes[0].set_ylabel("CAPM abnormal return since formation")
    axes[0].legend(loc="upper left")
    fig.suptitle("Excess CEO pay did not predict future returns in 2024–26",
                 x=0.01, ha="left", fontsize=15, fontweight="semibold", y=1.08)
    fig.text(0.01, 1.005, "Companies sorted into quintiles by 'excess pay' (residual of granted pay on TSR, size and sector, "
                          "using only data public at formation). Abnormal return = (R − Rf) − β(R_SPY − Rf).",
             fontsize=10, color=INK_2, ha="left")
    tm = st["cohorts"]["A"]["measures"]["capm_abnormal"]["top_movers"][0]
    _footer(fig, f"Raw equal-weighted means are dominated by single stocks (e.g. {tm['ticker']} "
                 f"{100 * tm['capm_abnormal']:+,.0f}pp in cohort A), so medians and winsorised means are shown. "
                 "Current-constituent sample: survivorship bias.\n" + SOURCE, y=-0.08)
    _save(fig, "07_strategy_test.png")


# ---------------------------------------------------------------------------
# 9. Portfolio backtest (daily, annual rebalance)
# ---------------------------------------------------------------------------
def backtest(r) -> None:
    bt = r.get("backtest")
    path = config.DATA_PROCESSED / "backtest_daily.csv"
    if not bt or not path.exists():
        return
    d = pd.read_csv(path, index_col=0, parse_dates=True)
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), gridspec_kw={"width_ratios": [1.35, 1]})
    ax = axes[0]
    series = [("SPY", "S&P 500 (SPY)", MUTED, 1.8), ("Q1 most underpaid", "Most underpaid fifth", BLUE, 2.2),
              ("Q5 most overpaid", "Most overpaid fifth", RED, 2.2)]
    for col, lab, colr, lw in series:
        g = (1 + d[col].fillna(0)).cumprod()
        ax.plot(g.index, g.values, color=colr, lw=lw, label=f"{lab}  {100 * (g.values[-1] - 1):+.0f}%")
    for dt in bt["rebalance_dates"][1:]:
        ax.axvline(pd.Timestamp(dt), color=AXIS, lw=1)
        ax.text(pd.Timestamp(dt), ax.get_ylim()[1], " rebalance", va="top", fontsize=8.5, color=MUTED)
    ax.set_ylabel("Growth of $1 (equal-weighted, dividends reinvested)")
    ax.legend(loc="upper left")
    ax.set_title("Cumulative growth")
    ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(bymonth=(1, 7)))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %Y"))
    ax = axes[1]
    ls = (1 + d["Long underpaid / short overpaid"].fillna(0)).cumprod()
    ax.fill_between(ls.index, 1, ls.values, color=ORANGE, alpha=0.18, lw=0)
    ax.plot(ls.index, ls.values, color=ORANGE, lw=2.2)
    ax.axhline(1, color=AXIS, lw=1)
    p = bt["portfolios"]["Long underpaid / short overpaid"]
    ax.set_title("Long underpaid / short overpaid", pad=22)
    ax.text(0, 1.015, f"Sharpe {p['sharpe']:.2f} · CAPM alpha {100 * p['alpha_ann']:+.1f}%/yr (t = {p['alpha_t']:.2f}) · "
                      f"beta {p['beta']:.2f}", transform=ax.transAxes, fontsize=9.5, color=INK_2, va="bottom")
    ax.set_ylabel("Growth of $1, zero-investment")
    ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(bymonth=(1, 7)))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %y"))
    q1, q5 = bt["portfolios"]["Q1 most underpaid"], bt["portfolios"]["Q5 most overpaid"]
    fig.suptitle("Backtest: buying 'underpaid' and shorting 'overpaid' earned no risk-adjusted return",
                 x=0.01, ha="left", fontsize=15, fontweight="semibold", y=1.06)
    fig.text(0.01, 0.995, f"{config.scope_label().replace('sample', 'Sample of ')}: fifths re-formed each 30 Sept on excess pay "
                          f"(~{bt['n_per_quintile']['Q1 most underpaid']} stocks each), daily returns {bt['start']} to {bt['end']}. "
                          f"Overpaid fifth beta {q5['beta']:.2f} vs underpaid {q1['beta']:.2f}: the raw gap is market risk.",
             fontsize=10, color=INK_2, ha="left")
    _footer(fig, "CAPM time-series regression with Newey-West (5-lag) t-statistics; risk-free = 13-week T-bill. "
                 "Today's index members only (survivorship bias).\n" + SOURCE, y=-0.06)
    _save(fig, "08_backtest.png")


def run() -> None:
    _style()
    r, m, res = _load()
    pay_vs_tsr(r, m, res)
    sector_breakdown(r)
    residuals(r, res)
    pay_mix(r)
    say_on_pay(r)
    tsr_crosscheck(r)
    strategy(r)
    backtest(r)
    linkedin(r, res)


if __name__ == "__main__":
    run()
