"""Phase 6b - Render the equity-research report (Markdown + PDF).

All statistics are pulled from ``output/results.json`` and the processed
CSVs at render time. Facts that come from filings rather than our dataset
(award sizes, vesting terms, board statements) are quoted with a citation to
the SEC document or news source, so every figure in the report is traceable.
"""
from __future__ import annotations

import json
import re
from datetime import date

import markdown
import pandas as pd

from . import config

P = config.DATA_PROCESSED


# ---------------------------------------------------------------------------
# Data access + formatting helpers
# ---------------------------------------------------------------------------
class Data:
    def __init__(self):
        self.r = json.loads((config.ROOT / "output" / "results.json").read_text())
        self.res = pd.read_csv(P / "residuals_3y.csv").set_index("ticker")
        self.panel = pd.read_csv(P / "master_panel.csv")
        self.sct = pd.read_csv(P / "sct_ceo_rows.csv")
        self.sop = pd.read_csv(P / "say_on_pay.csv")
        self.m = pd.read_csv(P / "master.csv").set_index("ticker")

    def co(self, tk: str) -> pd.Series:
        return self.res.loc[tk]

    def pay(self, tk: str, fy: int, col: str = "ceo_sct_total") -> float:
        g = self.panel[(self.panel["ticker"] == tk) & (self.panel["fy"] == fy)]
        return float(g[col].iloc[0])

    def comp(self, tk: str, fy: int, c: str) -> float:
        g = self.sct[(self.sct["ticker"] == tk) & (self.sct["fy"] == fy)]
        return float(g[c].iloc[0])

    def sop_list(self, tk: str) -> list[tuple[str, float]]:
        g = self.sop[self.sop["ticker"] == tk].sort_values("meeting_date")
        return list(zip(g["meeting_date"], g["support"]))

    def sop_url(self, tk: str, year: str) -> str:
        g = self.sop[(self.sop["ticker"] == tk) & self.sop["meeting_date"].str.startswith(year)]
        return g["url"].iloc[0]


def M(x: float, d: int = 1) -> str:
    """$ millions / billions."""
    if abs(x) >= 1e9:
        return f"${x / 1e9:,.{max(d, 1)}f}B"
    return f"${x / 1e6:,.{d}f}M"


def pct(x: float, d: int = 0, sign: bool = False) -> str:
    return f"{100 * x:{'+' if sign else ''}.{d}f}%"


def pv(p: float) -> str:
    if p < 0.001:
        return "p < 0.001"
    return f"p = {p:.3f}" if p < 0.1 else f"p = {p:.2f}"


def sops(d: Data, tk: str) -> str:
    return ", ".join(f"{pct(s, 0)} ({md[:4]})" for md, s in d.sop_list(tk))


# ---------------------------------------------------------------------------
# Sources (SEC first, news second)
# ---------------------------------------------------------------------------
SRC = {
    "ARES_proxy": "https://www.sec.gov/Archives/edgar/data/1176948/000162828026026286/ares-20260420.htm",
    "ARES_proxy24": "https://www.sec.gov/Archives/edgar/data/1176948/000162828024016964/ares-20240419.htm",
    "ARES_tipranks": "https://www.tipranks.com/news/company-announcements/ares-management-awards-executives-with-equity-incentives",
    "PANW_proxy": "https://www.sec.gov/Archives/edgar/data/1327567/000130817926000432/panw-20261027.htm",
    "PANW_tnw": "https://thenextweb.com/news/palo-alto-networks-arora-100m-pay-shareholders-reject",
    "BKNG_proxy": "https://www.sec.gov/Archives/edgar/data/1075531/000130817926000310/bkng-20260420.htm",
    "BKNG_skift": "https://skift.com/2026/04/14/booking-ceo-glenn-fogel-took-pay-cut-in-2025-after-2-big-years/",
    "GS_proxy": "https://www.sec.gov/Archives/edgar/data/886982/000119312526117433/gs-20260319.htm",
    "GS_bankingdive": "https://www.bankingdive.com/news/goldman-shareholders-back-80m-packages-for-solomon-waldron/746287/",
    "GS_amb": "https://www.americanbanker.com/news/goldman-shareholders-ok-executive-pay-but-with-less-support",
    "OMC_proxy": "https://www.sec.gov/Archives/edgar/data/29989/000121390026034811/ea0274271-02.htm",
    "OMC_8k": "https://www.sec.gov/Archives/edgar/data/29989/000121390025043442/ea0242158-8k_omnicom.htm",
    "OMC_campaign": "https://www.campaignlive.com/article/omnicom-ceo-john-wren-earned-70m-package-2025/1953453",
    "OMC_adnews": "https://www.adnews.com.au/news/omnicom-s-ceo-pay-was-cut-to-1-and-a-lot-of-shareholders-aren-t-impressed",
    "AMZN_proxy": "https://www.sec.gov/Archives/edgar/data/1018724/000110465926041026/tm261382-1_def14a.htm",
    "PLTR_proxy": "https://www.sec.gov/Archives/edgar/data/1321655/000132165526000019/pltr-20260423.htm",
    "PLTR_fortune": "https://fortune.com/2025/05/05/palantir-ceo-pay-alex-karp/",
    "PLTR_cnbc": "https://www.cnbc.com/2021/04/29/palantir-ceo-karp-earned-1point1-billion-in-2020-tied-to-equity-awards.html",
    "COIN_proxy": "https://www.sec.gov/Archives/edgar/data/1679788/000167978826000045/coin-20260424.htm",
    "COIN_blockworks": "https://blockworks.co/news/coinbase-ceo-compensation-bear-market",
}

DRIVER = {
    "ARES": "Incentive-fee allocations swapped for restricted units (2024-25)",
    "PANW": "Large annual PSU grants after a 2023 one-time retention award",
    "BKNG": "High target pay; peer group includes mega-cap tech",
    "GS": "$80M one-time retention RSUs (Jan 2025)",
    "WSM": "Not investigated in depth; no special award found in proxy scan",
    "AMZN": "No CEO equity grant since the 2021 promotion award",
    "PLTR": "Founder; pre-IPO mega-grant, no new awards",
    "COIN": "Founder; 2020 performance option, no new awards",
    "CINF": "CEO transition in window (flag); not investigated in depth",
    "KDP": "CEO transition in window (flag); not investigated in depth",
}


def outlier_table(d: Data, rows: list[dict]) -> str:
    out = ["| # | Company | CEO (latest FY) | Avg pay 3y | Model | vs model | TSR %/yr | Likely driver |",
           "|---|---|---|---:|---:|---:|---:|---|"]
    for o in rows:
        tk = o["ticker"]
        name = str(o["ceo_name_latest"]).replace("Mr. ", "").replace("Mr ", "") if o["ceo_name_latest"] == o["ceo_name_latest"] else "n/a"
        name = re.sub(r"\.(?=[A-Z])", ". ", name)
        out.append(f"| {int(o['resid_rank'])} | **{tk}** {o['company'][:22]} | {name[:20]} | {M(o['sct_avg_3y'])} | "
                   f"{M(o['predicted_pay'])} | {o['pay_vs_predicted_pct']:+.0f}% | {100 * o['tsr_3y_ann']:+.0f}% | "
                   f"{DRIVER.get(tk, '')} |")
    return "\n".join(out)


def reg_table(r: dict) -> str:
    out = ["| Window | Pay measure | +10 pp annual TSR → pay | p-value | R² (with size + sector) | n |",
           "|---|---|---:|---:|---:|---:|"]
    for n in config.WINDOWS:
        for y, lab in (("sct", "Granted (SCT)"), ("cap", "Actually paid (CAP)")):
            v = r["regressions"][f"{y}_{n}y_3_size_sector"]
            c = v["coefs"]["tsr_pp_w"]
            out.append(f"| {n} yr | {lab} | {v['pct_pay_per_10pp_tsr']:+.1f}% | {pv(c['p'])} | {100 * v['r2']:.0f}% | {v['n']} |")
    return "\n".join(out)


def robust_table(r: dict) -> str:
    rb = r["regressions"]["robustness_3y"]
    base = r["regressions"]["sct_3y_3_size_sector"]
    rows = [("Primary (3 yr, size + sector)", base, "tsr_pp_w"),
            ("Raw (un-winsorised) TSR", rb["raw_tsr"], "tsr_pp_raw"),
            ("Peer-relative TSR", rb["peer_relative_tsr"], "rel_tsr_pp"),
            ("Size = revenue", rb["revenue_size"], "tsr_pp_w"),
            ("Excl. CEO changes in window", rb["excl_ceo_change"], "tsr_pp_w"),
            ("CEO-seat pay (all PEOs summed)", rb["ceo_seat_pay"], "tsr_pp_w"),
            (f"Excl. no-equity-grant CEOs ({', '.join(rb['excl_no_equity_grants']['excluded'])})",
             rb["excl_no_equity_grants"], "tsr_pp_w")]
    out = ["| Granted-pay specification | +10 pp TSR → pay | p-value | n |", "|---|---:|---:|---:|"]
    for lab, v, key in rows:
        c = v["coefs"][key]
        out.append(f"| {lab} | {v['pct_pay_per_10pp_tsr']:+.1f}% | {pv(c['p'])} | {v['n']} |")
    rr = rb["rank_rank"]["coefs"]
    out.append(f"| Rank-rank (pay rank on TSR rank + size rank) | slope {rr['tsr_rank']['coef']:.2f} "
               f"(size {rr['mcap_rank']['coef']:.2f}) | {pv(rr['tsr_rank']['p'])} | {rb['rank_rank']['n']} |")
    return "\n".join(out)


# ---------------------------------------------------------------------------
def build_markdown() -> str:
    d = Data()
    r = d.r
    D, C, R, PM, SP, TQ = (r["descriptives"], r["correlations"], r["regressions"], r["pay_mix"],
                          r["say_on_pay"], r["tsr_quality"])
    n = config.PRIMARY_WINDOW_YEARS
    s1 = R[f"sct_{n}y_1_simple"]
    s3 = R[f"sct_{n}y_3_size_sector"]
    c1 = R[f"cap_{n}y_1_simple"]
    c3 = R[f"cap_{n}y_3_size_sector"]
    s5 = R["sct_5y_3_size_sector"]
    rb = R["robustness_3y"]
    xn = rb["excl_no_equity_grants"]
    rr = rb["rank_rank"]["coefs"]
    pan = r["panel"]
    o = r["outliers"]
    over, under = o["overpaid"], o["underpaid"]
    mis = o["misaligned_high_pay_low_tsr"]
    excl = ", ".join(xn["excluded"])

    # ---- per-company facts (all from our dataset) -------------------------
    ares, panw, bkng, amzn, pltr, coin, gs, omc = (d.co(t) for t in
                                                   ("ARES", "PANW", "BKNG", "AMZN", "PLTR", "COIN", "GS", "OMC"))
    amzn_2021 = d.pay("AMZN", 2021)
    gs_2025 = d.pay("GS", 2025)
    gs_retention = 80_000_099  # from GS 2026 DEF 14A Summary Compensation Table ("Retention RSUs")
    omc_2025 = d.pay("OMC", 2025)
    omc_opt = d.comp("OMC", 2025, "option")
    omc_prior = (d.pay("OMC", 2023) + d.pay("OMC", 2024)) / 2
    panw_fy23 = d.pay("PANW", 2023)
    pltr_caps = [d.pay("PLTR", y, "ceo_cap") for y in (2023, 2024, 2025)]
    coin_caps = [d.pay("COIN", y, "ceo_cap") for y in (2023, 2024, 2025)]

    names = d.m["company"].to_dict()
    over_tsr = [100 * x["tsr_3y_ann"] for x in over]
    failed = [names[f["ticker"]] for f in SP["failed_votes"]]
    secs = pd.DataFrame(r["sectors"])
    cap_sec = secs[secs["spearman_cap_tsr"] > 0.3]
    sct_sec = secs[secs["spearman_sct_tsr"] > 0.3].sort_values("sector")
    lo_sec = secs.loc[secs["median_sct_3y_musd"].idxmin()]
    hi_sec = secs.loc[secs["median_sct_3y_musd"].idxmax()]
    ranks = d.res
    ot = [x["ticker"] for x in over]
    ut = [x["ticker"] for x in under]
    over_worst_nofe = int(ranks.loc[ot, "rank_no_sector_fe"].max())
    over_worst_5y = int(ranks.loc[ot, "rank_window_5y"].max())
    alt_cols = ["rank_no_sector_fe", "rank_excl_no_equity"]
    under_best = int(ranks.loc[ut, alt_cols].min().min())  # highest-placed rank -> 'bottom X'
    under_bottom = o["n"] - under_best + 1
    amzn_5y_rank = int(ranks.loc["AMZN", "rank_window_5y"])
    under_ceo_change = [t for t in ut if bool(ranks.loc[t, "ceo_change_3y"])]
    under_founder = [t for t in ut if t not in under_ceo_change]
    xc = pd.read_csv(P / "tsr_crosscheck.csv")
    misdated = xc[xc["reasons"].fillna("").str.fullmatch("misdated")]["ticker"].tolist()
    misdated_txt = " and ".join(names[t] for t in misdated) or "none"

    def head(c: pd.Series) -> str:
        return (f"*3-yr avg granted pay {M(c['sct_avg_3y'])} vs {M(c['predicted_pay'])} predicted "
                f"({c['pay_vs_predicted_pct']:+.0f}%, rank {int(c['resid_rank'])} of {o['n']}); TSR "
                f"{100 * c['tsr_3y_ann']:+.0f}%/yr; avg CAP {M(c['cap_avg_3y'])}.*")

    today = date.today().strftime("%B %Y")
    md = f"""
<div class="masthead">
<div class="kicker">Equity Research · Governance &amp; Compensation · {today}</div>
<h1>Paid for Size, Not for Returns</h1>
<div class="dek">Do S&amp;P 500 CEOs get paid for shareholder returns? Evidence from {D['n_companies']} companies' SEC pay-versus-performance disclosures</div>
<div class="byline">Tyler Quezada · Sector-stratified sample of {D['n_companies']} S&amp;P 500 constituents · {D['n_company_years']} CEO-years (FY2021–FY2026)</div>
</div>

## Executive summary

- **Granted pay does not track returns.** Across {o['n']} companies, annualised 3-year TSR explains **{100 * s1['r2']:.1f}%** of the variation in the pay boards award (Summary Compensation Table). Each extra 10 points of annual TSR is associated with just **{s3['pct_pay_per_10pp_tsr']:+.1f}%** more pay after size and sector controls ({pv(s3['coefs']['tsr_pp_w']['p'])}). Within companies, pay does not respond to the same year's return either ({pv(pan['sct_same_year']['p'])}).
- **Realised pay does, largely by construction.** Compensation actually paid (CAP) marks equity to market; TSR explains **{100 * c1['r2']:.0f}%** of its variation and +10 points of TSR goes with roughly **{c3['pct_pay_per_10pp_tsr']:+.0f}%** more CAP ({pv(c3['coefs']['tsr_pp_w']['p'])}). Alignment comes from the stock CEOs already hold, not from boards adjusting new awards.
- **Size matters more than performance.** Granted pay ranks with company size (Spearman ρ = {C['3y']['sct_vs_mcap']['spearman_rho']:.2f}) far more than with TSR (ρ = {C['3y']['sct_vs_tsr']['spearman_rho']:.2f}). A weak link to TSR exists once four founder/lump-grant companies are set aside ({excl}): +10 points of TSR then means **{xn['pct_pay_per_10pp_tsr']:+.1f}%** pay ({pv(xn['coefs']['tsr_pp_w']['p'])}), versus **{100 * (2 ** xn['size_elasticity'] - 1):+.0f}%** for a doubling of market cap.
- **The biggest "overpaid" outliers were strong performers.** {', '.join(x['ticker'] for x in over)} were paid {over[-1]['pay_vs_predicted_pct']:.0f}–{over[0]['pay_vs_predicted_pct']:.0f}% above model, but all returned {min(over_tsr):.0f}–{max(over_tsr):.0f}%/yr. One-time or structural awards explain most of the gap. The "underpaid" end is dominated by founders and lumpy multi-year grants whose *realised* pay is enormous ({', '.join(under_founder)}), plus {len(under_ceo_change)} CEO transitions ({', '.join(under_ceo_change)}).
- **Shareholders notice.** Companies paying further above model receive lower say-on-pay support (ρ = {SP['corr_resid_support']['spearman_rho']:.2f}, {pv(SP['corr_resid_support']['spearman_p'])}); TSR itself is unrelated to support. {len(failed)} votes failed outright ({', '.join(failed)}).
- **Read proxy TSR with care.** {TQ['n_companies_flagged']} of {D['n_companies']} proxies contain TSR figures that miss market data by more than 10 points, mostly because earlier years were never rebased when the table rolled forward.

## Methodology

**Universe.** {D['n_companies']} of the 500 S&amp;P 500 issuers, drawn by proportional GICS-sector stratification (seed 42; `FULL_UNIVERSE=1` runs all 500).
**Pay.** CEO ("PEO") pay comes from the Item 402(v) pay-versus-performance XBRL (`ecd` taxonomy) in each company's latest DEF 14A, giving up to five fiscal years of SCT total pay, compensation actually paid and company/peer TSR. In multi-CEO years the year-end incumbent is used (flagged).
**Pay mix.** Pay mix is parsed from the Summary Compensation Table HTML. A row is kept only if its components sum to its total *and* that total equals the XBRL figure.
**Performance.** TSR is computed independently from Yahoo Finance prices with dividends reinvested, over each company's own fiscal windows (1, 3 and 5 years; 3 is primary). The proxy-reported TSR serves as a cross-check.
**Models.** OLS with HC3 robust errors: ln(average granted pay) and asinh(average CAP, $M) on annualised TSR (winsorised at 2.5/97.5%), ln(market cap at window start) and sector dummies.
**Outliers.** Outliers are the residuals of the granted-pay model. Say-on-pay votes are parsed from 8-K Item 5.07 filings ({SP['n_meetings']} meetings, {SP['n_companies']} companies). Every assumption is logged in `ASSUMPTIONS.md`.

## Key findings

**1. Pay boards grant barely moves with returns; pay CEOs realise moves a lot.** The contrast holds in every window:

{reg_table(r)}

Granted pay shows a significant link only over five years ({s5['pct_pay_per_10pp_tsr']:+.1f}% per 10 points, {pv(s5['coefs']['tsr_pp_w']['p'])}). The CAP-to-SCT ratio (median {D['cap_to_sct_median_3y']:.2f}x) has a rank correlation of {C['3y']['cap_to_sct_vs_tsr']['spearman_rho']:.2f} with TSR, and CAP exceeded granted pay in {pct(D['pct_ceo_years_cap_above_sct'])} of CEO-years.

![Pay vs TSR](../charts/01_pay_vs_tsr_scatter.png)

**2. The null result is robust, with one important exception.** No reasonable specification turns granted pay into a strong function of TSR:

{robust_table(r)}

The exception is the last row. {excl} paid their CEOs almost nothing in new equity during the window, yet delivered some of the highest returns in the sample. They flatten the linear fit. Without them, a modest positive slope appears. Rank methods, which down-weight such extremes, point the same way (slope {rr['tsr_rank']['coef']:.2f} on TSR rank vs {rr['mcap_rank']['coef']:.2f} on size rank). **Best reading: pay tracks performance weakly at best, and far less than it tracks size.**

**3. Sector view.** CAP's rank correlation with TSR exceeds 0.3 in {len(cap_sec)} of {len(secs)} sectors; granted pay's does in only {len(sct_sec)} ({', '.join(sct_sec['sector'])}). Median granted pay ranges from {M(lo_sec['median_sct_3y_musd'] * 1e6)} ({lo_sec['sector']}) to {M(hi_sec['median_sct_3y_musd'] * 1e6)} ({hi_sec['sector']}). With 4–17 firms per sector these are indicative only (`output/charts/02_sector_breakdown.png`).

**4. Pay mix does not predict returns.** The median CEO's 3-year pay is {pct(PM['median_mix']['equity'])} equity, {pct(PM['median_mix']['cash_incentive'])} cash incentive and {pct(PM['median_mix']['salary'])} salary; {pct(PM['share_using_options'])} of CEOs received options. Equity share is unrelated to TSR (ρ = {PM['corr']['equity']['spearman_rho']:.2f}, {pv(PM['corr']['equity']['spearman_p'])}; excluding the four no-grant CEOs ρ = {PM['excl_no_equity_grants']['corr_equity']['spearman_rho']:.2f}). A higher option share went with somewhat lower TSR (ρ = {PM['corr']['option']['spearman_rho']:.2f}, {pv(PM['corr']['option']['spearman_p'])}), a correlation that likely reflects sector and maturity rather than incentives (`04_pay_mix_by_tsr_quintile.png`).

**5. Shareholders punish the level of pay, not weak returns.** Median say-on-pay support was {pct(SP['median_support'], 1)}; {SP['n_below_70']} meetings fell below the 70% level proxy advisers treat as a warning. Support falls as the pay residual rises (ρ = {SP['corr_resid_support']['spearman_rho']:.2f}, {pv(SP['corr_resid_support']['spearman_p'])}) but is unrelated to TSR (ρ = {SP['corr_tsr_support']['spearman_rho']:.2f}, {pv(SP['corr_tsr_support']['spearman_p'])}). In a linear model controlling for TSR the residual effect is {SP['ols_support_on_resid_tsr']['coefs']['resid']['coef']:.1f} points of support per log point of excess pay ({pv(SP['ols_support_on_resid_tsr']['coefs']['resid']['p'])}), so the effect is real but modest (`05_say_on_pay_vs_residual.png`).

**6. Pay-versus-performance tables contain errors.** Our independent TSR matches the proxy within 1 point for {pct(TQ['share_within_1pt'])} of company-years (median gap {TQ['median_abs_gap_pts']:.2f} points). The errors cluster. {TQ['flag_reasons'].get('stale_base', 0)} companies carried earlier-year TSR forward from the prior year's base instead of restating it, and {misdated_txt} tagged its values one year early. Palantir's PvP table shows 2024 CEO pay of $4,630,170 while its Summary Compensation Table shows $4,360,170, a transposition in the same filing ([proxy]({SRC['PLTR_proxy']})). Multi-year proxy TSR should not be used without checking it against market data (`06_tsr_crosscheck.png`).

## Outliers: who is paid most above and below the model

Residuals from the primary model (granted pay on TSR, start-of-window size and sector; R² = {100 * o['r2']:.0f}%). "vs model" is actual pay relative to the model's prediction.

**Paid most above model ("overpaid relative to performance and size")**

{outlier_table(d, over)}

**Paid most below model ("underpaid")**

{outlier_table(d, under)}

All five above-model companies stay in the top {over_worst_nofe} when sector dummies are dropped and in the top {over_worst_5y} on a 5-year window. All five below-model companies stay in the bottom {under_bottom} without sector dummies or when the model is estimated without the no-grant companies. On a 5-year window Amazon moves to the middle (rank {amzn_5y_rank}) because that window includes its 2021 mega-grant, which independently confirms the timing explanation below. Because TSR barely moves predicted pay, these residuals mostly measure **pay relative to size and sector**. The classic case of high pay for weak returns appears instead in a misalignment screen of above-model pay with below-median TSR: {', '.join(f"{x['ticker']} ({x['pay_vs_predicted_pct']:+.0f}%, TSR {100 * x['tsr_3y_ann']:+.0f}%/yr)" for x in mis)}.

<img class="half" src="../charts/03_residual_outliers.png" alt="Residual outliers">

## Case studies

**Ares Management (ARES), Michael Arougheti: a pay structure, not a pay spike.** {head(ares)}
Arougheti draws no salary; Ares pays senior professionals mainly through carried interest and fund incentive fees. In January 2024 the board granted him **400,000 restricted units in exchange for reducing his incentive-fee allocations**, plus **250,000 more in January 2025** ([2026 proxy]({SRC['ARES_proxy']}); first described in the [2024 proxy]({SRC['ARES_proxy24']})). That conversion turns fee income into grant-date "stock awards": his reported stock awards rose from {M(d.comp('ARES', 2023, 'stock'))} (2023) to {M(d.comp('ARES', 2024, 'stock'))} (2024) and {M(d.comp('ARES', 2025, 'stock'))} (2025), on top of {M(d.comp('ARES', 2025, 'other'))} of 2025 "all other compensation" that the proxy attributes mainly to incentive-fee payments and carried-interest distributions. Ares is a controlled company and holds say-on-pay votes only every three years (last vote {sops(d, 'ARES')}). **Verdict:** explained. Alternative-asset-manager economics (performance fees routed through pay) and a one-off fee-for-equity swap, not a discretionary raise. Comparing ARES with corporate CEOs overstates "overpayment."

**Palo Alto Networks (PANW), Nikesh Arora: mega-grants and a failed vote.** {head(panw)}
In fiscal 2023 the board gave Arora a one-time performance-based RSU retention award; reported pay that year was {M(panw_fy23)}. Annual equity in FY2024–FY2026 remained very large ({M(d.pay('PANW', 2024))}, {M(d.pay('PANW', 2025))}, {M(d.pay('PANW', 2026))}). Shareholders supported pay with only {sops(d, 'PANW')} at the December meetings ([8-K]({d.sop_url('PANW', '2025')})); the company's latest proxy calls the 46% result "a call to action" and commits to no further overlapping one-time CEO awards and to fully performance-based FY2026 NEO equity ([2026 proxy]({SRC['PANW_proxy']})). Bloomberg reports seven rejected pay votes since 2015, the most in the S&amp;P 500 ([The Next Web]({SRC['PANW_tnw']})). **Verdict:** explained by deliberate mega-grants. TSR was strong, but shareholders judged the quantum excessive. This is the clearest governance case in the sample.

**Booking Holdings (BKNG), Glenn Fogel: no single event.** {head(bkng)}
Fogel's pay was consistently high ({M(d.pay('BKNG', 2023))}, {M(d.pay('BKNG', 2024))}, {M(d.pay('BKNG', 2025))} for 2023–25), almost all PSUs and RSUs ({M(d.comp('BKNG', 2023, 'stock'))}, {M(d.comp('BKNG', 2024, 'stock'))}, {M(d.comp('BKNG', 2025, 'stock'))} in stock awards). There was no one-time award. The compensation peer group mixes travel peers with mega-cap technology firms (Alphabet, Amazon, Meta, Microsoft, Adobe, Uber), which supports a high pay level ([2026 proxy]({SRC['BKNG_proxy']})). 2025 pay fell as stock awards shrank ([Skift]({SRC['BKNG_skift']})). Say-on-pay support stayed high: {sops(d, 'BKNG')}. **Verdict:** no clear one-off reason. The gap reflects a sustained board choice to pay at a mega-cap tech level, which shareholders accepted given {100 * bkng['tsr_3y_ann']:+.0f}%/yr returns. "Overpaid relative to size", but arguably paid for performance.

**Amazon (AMZN), Andy Jassy: a lumpy grant, not a pay cut.** {head(amzn)}
Jassy received no equity award in 2023–25. His reported pay was salary (${d.comp('AMZN', 2025, 'salary'):,.0f}) plus security and other costs. Amazon's proxy states the committee "has not granted Mr. Jassy an equity award since 2021" and that more than 80% of his 2021 promotion award vests in 2026–2031 ([2026 proxy]({SRC['AMZN_proxy']})). That 2021 award put his 2021 reported pay at {M(amzn_2021)}. Spread over its 10-year schedule it is about {M(amzn_2021 / 10)} a year, close to our model's {M(amzn['predicted_pay'])} prediction. Say-on-pay: {sops(d, 'AMZN')}. **Verdict:** explained. A timing artifact of multi-year front-loaded grants. Amazon is "underpaid" only in years without a grant.

**Palantir (PLTR), Alex Karp: lowest reported pay, highest realised pay.** {head(pltr)}
Karp's reported pay is salary ({M(d.comp('PLTR', 2025, 'salary'))}) plus security and other costs. His wealth comes from pre-IPO awards under the Executive Equity Plan: options on **141 million Class B shares at $11.38** plus RSUs ([2026 proxy]({SRC['PLTR_proxy']}); [CNBC]({SRC['PLTR_cnbc']})). As the stock rose {100 * pltr['tsr_3y_ann']:+.0f}%/yr, CAP reached {M(pltr_caps[0])}, {M(pltr_caps[1])} and {M(pltr_caps[2])} in 2023–25, the largest in the sample ([Fortune]({SRC['PLTR_fortune']})). Founders hold up to 49.999999% of voting power through Class F stock, so the {sops(d, 'PLTR')} say-on-pay result is not an independent verdict. **Verdict:** explained. Founder with a legacy mega-grant: "underpaid" on paper, the opposite in reality.

**Coinbase (COIN), Brian Armstrong: a 10-year option, priced in 2020.** {head(coin)}
The board has made no new equity grant to Armstrong since the August 2020 **CEO Performance Award**, a 10-year option on 9,293,911 shares that vests only at stock-price hurdles, starting after roughly 750% price growth and fully vesting around 1,600%. The board "does not anticipate" further awards during its term ([2026 proxy]({SRC['COIN_proxy']}); [Blockworks]({SRC['COIN_blockworks']})). Reported pay is a {M(d.comp('COIN', 2025, 'salary'))} salary plus personal security and aircraft costs ($7.6M and $1.1M in 2025, per the proxy). CAP swung with the stock: {M(coin_caps[0])}, {M(coin_caps[1])}, {M(coin_caps[2])} in 2023–25. Armstrong controls a majority of the vote (controlled company), and say-on-pay passed with {sops(d, 'COIN')}. **Verdict:** explained. Founder pay is front-loaded into a single price-hurdle option.

**Also notable.** *Goldman Sachs (#4 above model):* 2025 pay of {M(gs_2025)} includes **$80M of retention RSUs** that cliff-vest in January 2030 with no performance condition ([2026 proxy]({SRC['GS_proxy']})). Excluding it, 2025 pay was {M(gs_2025 - gs_retention)}. Support fell to {pct(d.sop_list('GS')[1][1])} in 2025 from {pct(d.sop_list('GS')[0][1])}, the weakest in about a decade, with ISS and Glass Lewis opposed ([Banking Dive]({SRC['GS_bankingdive']}); [American Banker]({SRC['GS_amb']})). *Omnicom (#1 on the misalignment screen):* Wren's 2025 pay of {M(omc_2025)} is almost entirely a **4,000,000-share option at $77.60** ({M(omc_opt)} grant value) granted in May 2025 when he cut his salary to $1 and gave up other incentive pay through fiscal 2028 ([2026 proxy]({SRC['OMC_proxy']}); [8-K]({SRC['OMC_8k']})). Spread over 2025–28 it is about {M(omc_2025 / 4)} a year, below his 2023–24 average of {M(omc_prior)}. Shareholders still objected: support fell from {pct(d.sop_list('OMC')[1][1])} to {pct(d.sop_list('OMC')[2][1])} ([Campaign]({SRC['OMC_campaign']}); [AdNews]({SRC['OMC_adnews']})). In both cases a 3-year average flatters or penalises a single front-loaded award.

## Limitations

- **Sample and survivorship.** n = {o['n']} current constituents. Firms that left the index after poor returns are missing, which biases TSR upward and may hide underperformers with high pay.
- **Short history.** PvP disclosure began with 2023 proxies, so at most five fiscal years (FY2021–FY2025 for most companies) are available. Grant-date SCT values are lumpy (AMZN, OMC, GS), and averaging only partly smooths them.
- **CAP is a paper measure.** CAP is mechanically linked to stock price, and companies apply the valuation rules unevenly. Its correlation with TSR is partly by construction.
- **Measurement.** Fiscal windows differ by year-end. Start-of-window market cap is approximated from current market cap and price change, ignoring buybacks. CEO-transition years use the incumbent ({D['n_ceo_change_3y']} companies had a change within the 3-year window).
- **Filing quality.** XBRL tagging errors exist (stale TSR bases, misdated values, Palantir's transposed pay figure). We use independent TSR and double-reconciled pay mix to contain them, but undetected errors remain possible.
- **Say-on-pay coverage.** Votes were parsed for {SP['n_companies']} of {D['n_companies']} companies. Support at controlled companies (ARES, COIN, PLTR) mostly reflects insider votes.
- **Causality.** All results are associations. Boards may set pay ex ante on expected performance, which cross-sectional data cannot identify.

## Conclusion

In this sample, boards set CEO pay mainly by company size and peer benchmarks; awarded pay responds little to the returns shareholders receive. Pay-for-performance alignment is real but runs through the stock: equity grants become worth far more or far less as the share price moves, which is why realised pay tracks TSR closely. The largest deviations from the size-and-sector norm come from deliberate structural choices: mega-grants at Palo Alto, fee-for-equity swaps at Ares, retention awards at Goldman, front-loaded options at Omnicom, and founder grants at Palantir, Coinbase and Amazon. They do not come from boards rewarding weak results. Investors should judge pay on realised outcomes and grant frequency rather than single-year headline numbers. They should also check proxy TSR against market data before relying on it.

<div class="sources">
<b>Data.</b> SEC EDGAR: DEF 14A pay-versus-performance XBRL (ecd taxonomy), Summary Compensation Tables, 8-K Item 5.07 vote results. Yahoo Finance: prices, dividends, market cap. Wikipedia: S&amp;P 500 constituents (CIKs verified against SEC). Results file: <code>output/results.json</code>. Full assumption log: <code>ASSUMPTIONS.md</code>.
</div>
"""
    return md.strip() + "\n"


CSS = """
@page { size: Letter; margin: 0.55in 0.6in 0.6in 0.6in;
        @bottom-right { content: counter(page) " / " counter(pages); font: 8pt Inter, sans-serif; color: #898781; }
        @bottom-left { content: "CEO Pay vs. Performance · S&P 500 sample"; font: 8pt Inter, sans-serif; color: #898781; } }
body { font-family: Inter, "Helvetica Neue", Arial, sans-serif; font-size: 8.8pt; line-height: 1.35; color: #0b0b0b; }
.masthead { border-bottom: 2px solid #0b0b0b; padding-bottom: 6px; margin-bottom: 8px; }
.kicker { font-size: 7.8pt; letter-spacing: 0.06em; text-transform: uppercase; color: #2a78d6; font-weight: 600; }
h1 { font-size: 21pt; margin: 2px 0 2px 0; letter-spacing: -0.01em; }
.dek { font-size: 10.5pt; color: #52514e; }
.byline { font-size: 8pt; color: #898781; margin-top: 3px; }
h2 { font-size: 11.5pt; margin: 11px 0 4px 0; padding-bottom: 2px; border-bottom: 1px solid #e1e0d9; }
p { margin: 3px 0 5px 0; text-align: left; }
ul { margin: 3px 0 5px 0; padding-left: 15px; }
li { margin-bottom: 3px; }
table { border-collapse: collapse; width: 100%; font-size: 7.6pt; margin: 4px 0 7px 0; }
th { text-align: left; font-weight: 600; border-bottom: 1px solid #0b0b0b; padding: 2px 4px; }
td { border-bottom: 1px solid #e1e0d9; padding: 2px 4px; vertical-align: top; }
img { width: 100%; margin: 4px 0 6px 0; }
img.half { width: 64%; display: block; margin: 2px auto 4px auto; }
a { color: #1c5cab; text-decoration: none; }
code { font-family: "JetBrains Mono", monospace; font-size: 7.6pt; }
.sources { font-size: 7.6pt; color: #52514e; border-top: 1px solid #e1e0d9; padding-top: 4px; margin-top: 8px; }
"""


def build_readme() -> str:
    """README with key findings rendered from the same results as the report."""
    d = Data()
    r = d.r
    D, C, R, SP, TQ, PM = (r["descriptives"], r["correlations"], r["regressions"], r["say_on_pay"],
                          r["tsr_quality"], r["pay_mix"])
    s1, s3, c1, c3 = (R["sct_3y_1_simple"], R["sct_3y_3_size_sector"], R["cap_3y_1_simple"],
                      R["cap_3y_3_size_sector"])
    xn = R["robustness_3y"]["excl_no_equity_grants"]
    o = r["outliers"]
    rows = []
    for x in o["overpaid"][:3] + o["underpaid"][:3]:
        rows.append(f"| {x['ticker']} | {x['company']} | {M(x['sct_avg_3y'])} | {M(x['predicted_pay'])} | "
                    f"{x['pay_vs_predicted_pct']:+.0f}% | {100 * x['tsr_3y_ann']:+.0f}% | {DRIVER.get(x['ticker'], '')} |")
    mis = ", ".join(f"{x['ticker']} ({x['pay_vs_predicted_pct']:+.0f}% vs model, TSR {100 * x['tsr_3y_ann']:+.0f}%/yr)"
                    for x in o["misaligned_high_pay_low_tsr"][:3])
    failed = ", ".join(sorted({f["ticker"] for f in SP["failed_votes"]}))
    return f"""# CEO Pay vs. Performance: Do S&P 500 CEOs Get Paid for Shareholder Returns?

An end-to-end equity-research project: it pulls CEO pay from SEC pay-versus-performance XBRL filings,
rebuilds total shareholder return (TSR) independently from market data, tests whether pay tracks
returns, and investigates the biggest outliers with primary sources.

<p align="center"><img src="output/charts/linkedin_summary.png" width="420" alt="Summary chart"></p>

## Key findings

*{D['n_companies']}-company, sector-stratified S&P 500 sample; {D['n_company_years']} CEO-years; primary window = each company's latest 3 fiscal years (mostly FY2023–FY2025).*

1. **Granted pay does not track returns.** 3-year annualised TSR explains **{100 * s1['r2']:.1f}%** of the variation in the
   pay boards award (Summary Compensation Table). After size and sector controls, +10 points of annual TSR goes with
   **{s3['pct_pay_per_10pp_tsr']:+.1f}%** pay (p = {s3['coefs']['tsr_pp_w']['p']:.2f}). Within companies, pay does not move with the same year's
   TSR (p = {r['panel']['sct_same_year']['p']:.2f}).
2. **Realised pay does.** TSR explains **{100 * c1['r2']:.0f}%** of the variation in *compensation actually paid* (CAP);
   +10 points of TSR ≈ **{c3['pct_pay_per_10pp_tsr']:+.0f}%** CAP (p < 0.001). Alignment runs through the stock CEOs already hold.
3. **Size matters more than performance.** Pay ranks track company size (Spearman ρ = {C['3y']['sct_vs_mcap']['spearman_rho']:.2f}) far more
   than TSR (ρ = {C['3y']['sct_vs_tsr']['spearman_rho']:.2f}). Excluding four founder/lump-grant companies ({', '.join(xn['excluded'])}), a modest
   link appears: +10 points of TSR ≈ {xn['pct_pay_per_10pp_tsr']:+.1f}% pay (p = {xn['coefs']['tsr_pp_w']['p']:.3f}) vs {100 * (2 ** xn['size_elasticity'] - 1):+.0f}% for doubling market cap.
4. **The biggest "overpaid" outliers were strong performers.** Their excess pay traces to structural or one-time awards:
   Ares' fee-for-equity swap, Palo Alto's mega-grants (a failed {pct(min(v for _, v in d.sop_list('PANW')))} say-on-pay vote), Goldman's $80M retention RSUs.
   The "underpaid" end is founders and lumpy multi-year grants (Amazon, Palantir, Coinbase) whose *realised* pay is enormous.
   The classic high-pay/weak-return case appears in a misalignment screen: {mis}.
5. **Shareholders react to the level of pay, not to returns.** Above-model pay gets lower say-on-pay support
   (ρ = {SP['corr_resid_support']['spearman_rho']:.2f}, p = {SP['corr_resid_support']['spearman_p']:.3f}); TSR is unrelated (p = {SP['corr_tsr_support']['spearman_p']:.2f}). Failed votes in sample: {failed}.
6. **Proxy TSR contains errors.** Our independent TSR matches the proxy within 1 point for {100 * TQ['share_within_1pt']:.0f}% of
   company-years, but {TQ['n_companies_flagged']} of {D['n_companies']} PvP tables are off by more than 10 points, mostly because earlier years
   were never rebased when the table rolled forward.
7. **Pay mix does not predict returns.** Median CEO pay is {100 * PM['median_mix']['equity']:.0f}% equity; equity share is unrelated to TSR
   (ρ = {PM['corr']['equity']['spearman_rho']:.2f}).

### Outliers (residuals from `ln(granted pay) ~ TSR + ln(market cap) + sector`)

| Ticker | Company | 3-yr avg pay | Model | vs model | TSR/yr | Likely driver |
|---|---|---:|---:|---:|---:|---|
{chr(10).join(rows)}

Full case studies with SEC and news citations are in [`output/report/report.pdf`](output/report/report.pdf).

## Deliverables

| Path | What |
|---|---|
| [`output/report/report.pdf`](output/report/report.pdf) / [`.md`](output/report/report.md) | 5-page equity-research write-up |
| [`notebooks/analysis.ipynb`](notebooks/analysis.ipynb) | Full walkthrough; runs top to bottom offline |
| [`output/charts/`](output/charts) | Pay-vs-TSR scatter, sector breakdown, residual outliers, pay mix, say-on-pay, TSR cross-check |
| [`output/charts/linkedin_summary.png`](output/charts/linkedin_summary.png) | Standalone 1080x1350 summary graphic |
| [`data/processed/master.csv`](data/processed/master.csv) | Tidy company-level dataset ({D['n_companies']} rows) |
| [`data/processed/master_panel.csv`](data/processed/master_panel.csv) | Company x fiscal-year panel |
| [`output/results.json`](output/results.json) | Every statistic quoted in the report |
| [`output/tables/`](output/tables) | Regression, sector, outlier, pay-mix and say-on-pay tables (chart table views) |
| [`ASSUMPTIONS.md`](ASSUMPTIONS.md) | Every judgment call, with rationale and impact |

## How to reproduce

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export SEC_CONTACT_EMAIL="you@example.com"     # SEC requires a contact in the User-Agent
python -m src.pipeline --notebook               # ~10 min cold, seconds when cached
```

* `FULL_UNIVERSE=1 python -m src.pipeline` runs all ~500 S&P 500 companies instead of the 100-company sample.
* All downloads are cached in `data/raw/` (git-ignored), so nothing is fetched twice. SEC requests are throttled to 8/s.
* The notebook reproduces the analysis offline from the committed `data/processed/` files.

## Method in brief

* **Universe.** S&P 500 constituents, GICS sectors and CIKs from Wikipedia, with CIKs verified against SEC. The sample uses proportional sector stratification (seed 42).
* **Pay.** The `ecd` pay-versus-performance XBRL in each latest DEF 14A gives `PeoTotalCompAmt`, `PeoActuallyPaidCompAmt`, `TotalShareholderRtnAmt` and `PeerGroupTotalShareholderRtnAmt`. Multi-CEO years come from `ecd:IndividualAxis`; the year-end incumbent is used and flagged. The Summary Compensation Table is parsed from HTML for pay mix, keeping only rows that reconcile to the XBRL total.
* **Performance.** TSR is a dividend-reinvested total-return index from yfinance, over each company's own fiscal windows (1/3/5 years). It is cross-checked against proxy TSR, and gaps are diagnosed automatically.
* **Models.** OLS with HC3 errors, using winsorised TSR, start-of-window log market cap and sector fixed effects. Robustness covers raw TSR, peer-relative TSR, revenue size, CEO-seat pay, CEO-change exclusions and rank-rank models. The panel adds company and year fixed effects.
* **Evidence.** Say-on-pay results come from 8-K Item 5.07 ({SP['n_meetings']} meetings), plus CD&A keyword extraction, proxy reading and news.

## Data sources

* SEC EDGAR: submissions API, DEF 14A filings and XBRL instances, 8-K Item 5.07 vote results.
* Yahoo Finance via `yfinance`: daily prices, dividends, splits, market cap, income statement.
* Wikipedia: *List of S&P 500 companies* (constituents, GICS sector, CIK).

## Limitations

Current-constituent sample (survivorship bias); n ≈ 100; 1–5 years of PvP history; lumpy grant-date values;
CAP is a mark-to-market measure partly linked to TSR by construction; approximated start-of-window market cap;
filing errors; correlation, not causation. See the report and `ASSUMPTIONS.md`.

*Research project for educational purposes; not investment advice.*
"""


def build() -> None:
    (config.ROOT / "README.md").write_text(build_readme())
    md = build_markdown()
    out_md = config.REPORT / "report.md"
    out_md.write_text(md)
    html_body = markdown.markdown(md, extensions=["tables", "md_in_html"])
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{html_body}</body></html>"
    (config.REPORT / "report.html").write_text(html)
    from weasyprint import HTML
    doc = HTML(string=html, base_url=str(config.REPORT)).render()
    doc.write_pdf(config.REPORT / "report.pdf")
    print(f"[report] report.md, report.pdf ({len(doc.pages)} pages)")


if __name__ == "__main__":
    build()
