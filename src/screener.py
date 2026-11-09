"""Interactive CEO pay screener (self-contained HTML).

    python -m src.screener

Builds one verified record per company from data/processed + results.json and
writes:
* output/screener/screener.html  - page body for publishing as a claude.ai Artifact
* output/screener/index.html     - the same page as a standalone document (open in any browser)

The optional "AI analyst" asks Claude about one company using ONLY that
company's verified record, then checks every number in the answer against the
record and highlights any figure it cannot match. It needs the claude.ai
viewer (the `sample` capability); everywhere else it hides itself.
"""
from __future__ import annotations

import json
import math

import pandas as pd

from . import config

P = config.DATA_PROCESSED
OUT = config.ROOT / "output" / "screener"
OUT.mkdir(parents=True, exist_ok=True)
REPO = "https://github.com/tylerq05-maker/ceo-pay-vs-performance"


def _f(x, nd=4):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), nd)


def case_notes(panel: pd.DataFrame, sct: pd.DataFrame) -> dict:
    """Verified case-study notes (facts from the SEC filings; figures from our data)."""
    def pay(t, fy, col="ceo_sct_total"):
        return float(panel[(panel.ticker == t) & (panel.fy == fy)][col].iloc[0])

    def comp(t, fy, c):
        return float(sct[(sct.ticker == t) & (sct.fy == fy)][c].iloc[0])

    M = lambda v: f"${v / 1e9:.1f}B" if abs(v) >= 1e9 else f"${v / 1e6:.1f}M"  # noqa: E731
    omc25 = pay("OMC", 2025)
    src = {
        "ARES": [("2026 proxy", "https://www.sec.gov/Archives/edgar/data/1176948/000162828026026286/ares-20260420.htm"),
                 ("2024 proxy", "https://www.sec.gov/Archives/edgar/data/1176948/000162828024016964/ares-20240419.htm")],
        "PANW": [("2026 proxy", "https://www.sec.gov/Archives/edgar/data/1327567/000130817926000432/panw-20261027.htm"),
                 ("The Next Web", "https://thenextweb.com/news/palo-alto-networks-arora-100m-pay-shareholders-reject")],
        "BKNG": [("2026 proxy", "https://www.sec.gov/Archives/edgar/data/1075531/000130817926000310/bkng-20260420.htm"),
                 ("Skift", "https://skift.com/2026/04/14/booking-ceo-glenn-fogel-took-pay-cut-in-2025-after-2-big-years/")],
        "GS": [("2026 proxy", "https://www.sec.gov/Archives/edgar/data/886982/000119312526117433/gs-20260319.htm"),
               ("Banking Dive", "https://www.bankingdive.com/news/goldman-shareholders-back-80m-packages-for-solomon-waldron/746287/")],
        "AMZN": [("2026 proxy", "https://www.sec.gov/Archives/edgar/data/1018724/000110465926041026/tm261382-1_def14a.htm")],
        "PLTR": [("2026 proxy", "https://www.sec.gov/Archives/edgar/data/1321655/000132165526000019/pltr-20260423.htm"),
                 ("Fortune", "https://fortune.com/2025/05/05/palantir-ceo-pay-alex-karp/")],
        "COIN": [("2026 proxy", "https://www.sec.gov/Archives/edgar/data/1679788/000167978826000045/coin-20260424.htm"),
                 ("Blockworks", "https://blockworks.co/news/coinbase-ceo-compensation-bear-market")],
        "OMC": [("2026 proxy", "https://www.sec.gov/Archives/edgar/data/29989/000121390026034811/ea0274271-02.htm"),
                ("8-K, May 2025", "https://www.sec.gov/Archives/edgar/data/29989/000121390025043442/ea0242158-8k_omnicom.htm")],
    }
    notes = {
        "ARES": ("Explained: pay structure",
                 "Arougheti takes no salary; Ares pays senior people mainly through carried interest and fund incentive fees. "
                 "In Jan-2024 the board granted him 400,000 restricted units in exchange for lower incentive-fee allocations, "
                 f"and 250,000 more in Jan-2025. That turns fee income into reported stock awards ({M(comp('ARES', 2024, 'stock'))} "
                 f"in 2024, {M(comp('ARES', 2025, 'stock'))} in 2025). Ares is a controlled company and holds say-on-pay votes "
                 "every three years."),
        "PANW": ("Explained: mega-grants and a failed vote",
                 f"A one-time performance-based RSU retention award in fiscal 2023 (reported pay {M(pay('PANW', 2023))}) was "
                 "followed by very large annual grants. Shareholders gave only 46% support in Dec-2025; the 2026 proxy commits "
                 "to no further overlapping one-time CEO awards. Bloomberg counts seven rejected pay votes since 2015."),
        "BKNG": ("No single cause: a sustained pay level",
                 "There was no one-time award: pay is consistently high and almost all PSUs and RSUs. The compensation peer "
                 "group includes Alphabet, Amazon, Meta and Microsoft alongside travel companies. Say-on-pay support stayed "
                 "around 88-90%, likely because returns were strong."),
        "GS": ("Explained: one-time retention award",
               f"2025 pay of {M(pay('GS', 2025))} includes $80M of retention RSUs (130,508 units at $612.99, Jan-2025) that "
               "cliff-vest in January 2030 with no performance condition. Say-on-pay support fell to 66% in 2025."),
        "AMZN": ("Explained: grant timing",
                 "Jassy has received no equity award since his 2021 promotion grant, which put 2021 reported pay at "
                 f"{M(pay('AMZN', 2021))}; more than 80% of it vests in 2026-2031. Spread over 10 years it is about "
                 f"{M(pay('AMZN', 2021) / 10)} a year."),
        "PLTR": ("Explained: founder with a legacy grant",
                 "Karp's wealth comes from pre-IPO awards: options on 141,000,000 Class B shares at $11.38 plus RSUs. Realised "
                 f"pay (CAP) was {M(pay('PLTR', 2023, 'ceo_cap'))}, {M(pay('PLTR', 2024, 'ceo_cap'))} and "
                 f"{M(pay('PLTR', 2025, 'ceo_cap'))} in 2023-25. Founders hold up to 49.999999% of the vote."),
        "COIN": ("Explained: founder performance option",
                 "The August 2020 CEO Performance Award is a 10-year option on 9,293,911 shares that vests only at stock-price "
                 "hurdles (from about 750% to 1,600% price growth); the board does not plan further awards during its term. "
                 "Coinbase is a controlled company."),
        "OMC": ("Explained: front-loaded option",
                f"Wren's 2025 pay of {M(omc25)} is mostly a 4,000,000-share option at $77.60 granted in May-2025, when he cut "
                f"his salary to $1 and gave up other incentive pay through fiscal 2028. Spread over 2025-28 it is about "
                f"{M(omc25 / 4)} a year. Say-on-pay support fell to 56% in 2026."),
    }
    return {t: {"verdict": v, "text": txt, "sources": [{"label": a, "url": b} for a, b in src[t]]}
            for t, (v, txt) in notes.items()}


def build_data() -> dict:
    r = json.loads((config.ROOT / "output" / "results.json").read_text())
    m = pd.read_csv(P / "master.csv")
    res = pd.read_csv(P / "residuals_3y.csv").set_index("ticker")
    panel = pd.read_csv(P / "master_panel.csv")
    sct = pd.read_csv(P / "sct_ceo_rows.csv")
    sop = pd.read_csv(P / "say_on_pay.csv")
    sm = pd.read_csv(config.ROOT / "output" / "validation" / "source_match_by_company.csv").set_index("ticker")
    strat = pd.read_csv(P / "strategy_cohorts.csv")
    fis = pd.read_csv(P / "tsr_fiscal.csv")
    notes = case_notes(panel, sct)
    mis = {x["ticker"] for x in r["outliers"]["misaligned_high_pay_low_tsr"]}
    med_tsr = res["tsr_3y_ann"].median()

    cos = []
    for row in m.itertuples():
        t = row.ticker
        g = panel[panel.ticker == t].sort_values("fy")
        rr = res.loc[t] if t in res.index else None
        s = sop[sop.ticker == t].sort_values("meeting_date")
        st = strat[strat.ticker == t].set_index("cohort")
        gaps = fis[fis.ticker == t]["diff_pts"].abs()
        rec = {
            "t": t, "n": row.company, "s": row.sector,
            "ceo": None if pd.isna(row.ceo_name_latest) else str(row.ceo_name_latest),
            "fy": int(row.latest_fy),
            "pay3": _f(row.sct_avg_3y, 0), "cap3": _f(row.cap_avg_3y, 0),
            "tsr3": _f(row.tsr_3y_ann), "tsr1": _f(row.tsr_1y), "tsr5": _f(row.tsr_5y_ann),
            "peer3": _f(row.peer_tsr_3y), "mcap": _f(row.yf_marketCap, 0),
            "pred": _f(rr["predicted_pay"], 0) if rr is not None else None,
            "vs": _f(rr["pay_vs_predicted_pct"], 1) if rr is not None else None,
            "rank": int(rr["resid_rank"]) if rr is not None else None,
            "alt": ({k: (None if pd.isna(rr[c]) else int(rr[c])) for k, c in
                     (("nofe", "rank_no_sector_fe"), ("cap", "rank_cap_model"), ("w5", "rank_window_5y"),
                      ("exnoeq", "rank_excl_no_equity"))} if rr is not None else None),
            "years": [{"fy": int(y.fy), "sct": _f(y.ceo_sct_total, 0), "cap": _f(y.ceo_cap, 0),
                       "tsr": _f(y.indep_tsr_annual), "peos": int(y.n_peos) if not pd.isna(y.n_peos) else 1,
                       "ceo": None if pd.isna(y.ceo_name) else str(y.ceo_name)} for y in g.itertuples()],
            "mix": None if pd.isna(row.mix_equity) else {
                "salary": _f(row.mix_salary), "cash": _f(row.mix_cash_incentive), "stock": _f(row.mix_stock),
                "option": _f(row.mix_option), "other": _f((row.mix_pension or 0) + (row.mix_other or 0)),
                "years": int(row.mix_years)},
            "sop": [{"d": x.meeting_date, "s": _f(x.support)} for x in s.itertuples()],
            "flags": {
                "ceo_change": bool(row.ceo_change_3y) if not pd.isna(row.ceo_change_3y) else False,
                "co_ceo": bool(row.co_ceo),
                "tsr_issue": None if not row.tsr_discrepancy else str(row.tsr_discrepancy_reason),
                "misaligned": t in mis,
                "low_sop": bool(len(s) and s["support"].min() < 0.7),
            },
            "checks": {"pay_in_proxy": bool(sm.loc[t, "sct_in_proxy"]) if t in sm.index else None,
                       "cap_in_proxy": bool(sm.loc[t, "cap_in_proxy"]) if t in sm.index else None,
                       "mix_years": None if pd.isna(row.mix_years) else int(row.mix_years),
                       "tsr_gap": _f(gaps.max(), 2) if len(gaps.dropna()) else None,
                       "tsr_gap_median": _f(gaps.median(), 2) if len(gaps.dropna()) else None},
            "strat": {c: {"q": str(st.loc[c, "quintile"]), "ar": _f(st.loc[c, "capm_abnormal"]),
                          "formed": str(st.loc[c, "formation"])} for c in st.index},
            "url": row.proxy_url,
            "note": notes.get(t),
        }
        rec["flags"]["any"] = bool(rec["flags"]["misaligned"] or rec["flags"]["low_sop"] or
                                   rec["flags"]["tsr_issue"] or (rec["rank"] is not None and
                                                                 (rec["rank"] <= 5 or rec["rank"] >= 95)))
        cos.append(rec)

    R = r["regressions"]
    meta = {
        "n": r["outliers"]["n"], "n_companies": r["descriptives"]["n_companies"],
        "median_pay3": r["descriptives"]["median_sct_3y"], "median_tsr3": float(med_tsr),
        "median_cap3": r["descriptives"]["median_cap_3y"],
        "sct_r2": R["sct_3y_1_simple"]["r2"], "cap_r2": R["cap_3y_1_simple"]["r2"],
        "sct_effect": R["sct_3y_3_size_sector"]["pct_pay_per_10pp_tsr"],
        "sct_p": R["sct_3y_3_size_sector"]["coefs"]["tsr_pp_w"]["p"],
        "cap_effect": R["cap_3y_3_size_sector"]["pct_pay_per_10pp_tsr"],
        "model_r2": r["outliers"]["r2"],
        "fit": {"sct": [R["sct_3y_1_simple"]["coefs"]["Intercept"]["coef"], R["sct_3y_1_simple"]["coefs"]["tsr_pp_w"]["coef"]],
                "cap": [R["cap_3y_1_simple"]["coefs"]["Intercept"]["coef"], R["cap_3y_1_simple"]["coefs"]["tsr_pp_w"]["coef"]],
                "winsor": r["descriptives"]["winsor_bounds_3y_pp"]},
        "rho_size": r["correlations"]["3y"]["sct_vs_mcap"]["spearman_rho"],
        "rho_tsr": r["correlations"]["3y"]["sct_vs_tsr"]["spearman_rho"],
        "sop_rho": r["say_on_pay"]["corr_resid_support"]["spearman_rho"],
        "strategy_ic": {k: v["measures"]["capm_abnormal"]["rank_ic"]["spearman_rho"]
                        for k, v in r["strategy"]["cohorts"].items()},
        "strategy_p": {k: v["measures"]["capm_abnormal"]["rank_ic"]["spearman_p"]
                       for k, v in r["strategy"]["cohorts"].items()},
        "repo": REPO,
    }
    v = json.loads((config.ROOT / "output" / "validation" / "validation.json").read_text())
    meta["validation"] = {
        "perm_p_sct": v["permutation"]["sct"]["perm_p_two_sided"],
        "boot_sct": v["bootstrap"]["sct"]["ci95_pct_pay_per_10pp"],
        "source_match": f"{v['source_match']['sct_found']}/{v['source_match']['n']}",
        "mix": f"{v['mix_reconciliation']['xbrl_match_pass']}/{v['mix_reconciliation']['rows']}",
        "claims": f"{sum(c['verified'] for c in v['claims'])}/{len(v['claims'])}",
        "tsr_median_gap": v["tsr"]["median_abs_gap_pts"],
    }
    return {"meta": meta, "companies": cos}


def build() -> None:
    data = build_data()
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    body = TEMPLATE.replace("/*__DATA__*/", payload)
    (OUT / "screener.html").write_text(body)
    doc = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
           "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">"
           "</head><body>" + body + "</body></html>")
    (OUT / "index.html").write_text(doc)
    print(f"[screener] {len(data['companies'])} companies -> output/screener/index.html "
          f"({len(doc) / 1024:.0f} KB)")


TEMPLATE = r"""<title>CEO Pay Alignment Screener</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: analyst desk. Left = thesis, scatter, ranked ledger; right = one company's dossier. */
:root{
  --bg:#f3f5f7; --panel:#ffffff; --ink:#122033; --ink-2:#465467; --muted:#7a8696; --line:#dde3ea; --grid:#e9edf2;
  --accent:#1f5fbf; --over:#cf3f37; --under:#2a72cf; --ok:#1d7f49; --warn:#a86a12; --chip:#eef2f7; --hi:#fff4d6;
  --mix1:#2a78d6; --mix2:#eb6834; --mix3:#1baf7a; --mix4:#eda100; --mix5:#e87ba4;
  --f-display:"Archivo","Helvetica Neue",Arial,sans-serif; --f-body:"IBM Plex Sans","Helvetica Neue",Arial,sans-serif;
  --f-mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#0c1219; --panel:#131b25; --ink:#e6ecf3; --ink-2:#b3bfcc; --muted:#8392a3; --line:#253141; --grid:#1c2633;
  --accent:#7aa8ff; --over:#f06b62; --under:#62a4f2; --ok:#4cc38a; --warn:#e3ad4a; --chip:#1a2431; --hi:#3a3216;
  --mix1:#3987e5; --mix2:#d95926; --mix3:#199e70; --mix4:#c98500; --mix5:#d55181; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0c1219; --panel:#131b25; --ink:#e6ecf3; --ink-2:#b3bfcc; --muted:#8392a3; --line:#253141; --grid:#1c2633;
  --accent:#7aa8ff; --over:#f06b62; --under:#62a4f2; --ok:#4cc38a; --warn:#e3ad4a; --chip:#1a2431; --hi:#3a3216;
  --mix1:#3987e5; --mix2:#d95926; --mix3:#199e70; --mix4:#c98500; --mix5:#d55181; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:15px/1.5 var(--f-body);margin:0}
.wrap{max-width:1320px;margin:0 auto;padding-block:20px 40px;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
a{color:var(--accent)}
.kicker{font:600 12px/1.2 var(--f-body);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
h1{font:800 clamp(28px,4.2vw,44px)/1.05 var(--f-display);letter-spacing:-.015em;margin:6px 0 8px;text-wrap:balance}
h2{font:700 17px/1.2 var(--f-display);margin:0;text-wrap:balance}
h3{font:600 12px/1.2 var(--f-body);letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin:0 0 8px}
.lede{color:var(--ink-2);max-width:68ch;margin:0}
.facts{display:flex;flex-wrap:wrap;gap:10px 28px;margin:16px 0 18px;padding:12px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.fact{min-width:0}
.fact b{display:block;font:600 22px/1.1 var(--f-mono)}
.fact span{font-size:12.5px;color:var(--muted)}
.grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);gap:18px;align-items:start}
@media (max-width:980px){.grid{grid-template-columns:minmax(0,1fr)}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;min-width:0}
.stack{display:grid;gap:18px;min-width:0}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{border:0;background:transparent;color:var(--ink-2);font:500 13px var(--f-body);padding:7px 12px;cursor:pointer}
.seg button[aria-pressed="true"]{background:var(--ink);color:var(--panel)}
select,input[type=search],textarea{font:14px var(--f-body);color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:7px 10px}
input[type=search]{min-width:0;flex:1 1 160px}
label.tog{display:inline-flex;gap:6px;align-items:center;font-size:13px;color:var(--ink-2);cursor:pointer}
button:focus-visible,select:focus-visible,input:focus-visible,textarea:focus-visible,tr:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12.5px;color:var(--ink-2);margin-top:6px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:-1px}
.chart-wrap{position:relative}
svg{display:block;width:100%;height:auto}
svg{--chart-fs:11}
svg text{fill:var(--muted);font:11px var(--f-mono)}
@media (max-width:640px){svg{--chart-fs:17} svg text{font-size:17px}}
.tip{position:absolute;pointer-events:none;background:var(--ink);color:var(--panel);font-size:12.5px;padding:6px 9px;border-radius:6px;white-space:nowrap;transform:translate(-50%,-110%)}
.tblwrap{overflow:auto;max-height:520px;border-top:1px solid var(--line)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{position:sticky;top:0;background:var(--panel);text-align:left;font:600 12px var(--f-body);color:var(--muted);padding:8px 8px;border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap}
th[aria-sort] {color:var(--ink)}
td{padding:7px 8px;border-bottom:1px solid var(--grid);white-space:nowrap}
td.num,th.num{text-align:right;font-family:var(--f-mono);font-variant-numeric:tabular-nums}
tbody tr{cursor:pointer}
tbody tr:hover{background:var(--chip)}
tbody tr[aria-selected="true"]{background:var(--hi)}
.tk{font:600 13px var(--f-mono)}
.sub{color:var(--muted);font-size:12px}
.pill{display:inline-block;font:600 11.5px var(--f-body);padding:2px 8px;border-radius:999px;background:var(--chip);color:var(--ink-2)}
.pill.over{background:color-mix(in srgb,var(--over) 15%,transparent);color:var(--over)}
.pill.under{background:color-mix(in srgb,var(--under) 15%,transparent);color:var(--under)}
.pill.warn{background:color-mix(in srgb,var(--warn) 16%,transparent);color:var(--warn)}
.pill.ok{background:color-mix(in srgb,var(--ok) 15%,transparent);color:var(--ok)}
.dossier{position:sticky;top:max(12px,env(safe-area-inset-top,0px))}
@media (max-width:980px){.dossier{position:static}}
.dhead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}
.dhead .name{font:800 24px/1.1 var(--f-display)}
.kv{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 16px;margin:14px 0}
.kv div{min-width:0}
.kv b{display:block;font:500 17px var(--f-mono)}
.kv span{font-size:12px;color:var(--muted)}
.bars{display:grid;gap:6px;margin:6px 0 2px}
.bar{display:grid;grid-template-columns:76px minmax(0,1fr) 72px;gap:8px;align-items:center;font-size:12.5px}
.bar .tr{height:12px;background:var(--grid);border-radius:3px;overflow:hidden}
.bar .fl{height:100%;border-radius:3px}
.bar .v{font-family:var(--f-mono);text-align:right}
.sec{border-top:1px solid var(--line);padding-top:12px;margin-top:14px}
.mixbar{display:flex;height:16px;border-radius:4px;overflow:hidden;gap:2px;background:var(--panel)}
.mixbar span{display:block;height:100%}
.checks{list-style:none;padding:0;margin:0;display:grid;gap:5px;font-size:13px}
.checks li{display:flex;gap:8px;align-items:baseline}
.checks .ic{font:600 12px var(--f-mono);min-width:18px}
.ic.ok{color:var(--ok)} .ic.warn{color:var(--warn)}
.note{background:var(--chip);border-radius:8px;padding:10px 12px;font-size:13.5px}
.note b{display:block;margin-bottom:4px}
.ai textarea{width:100%;min-height:58px;resize:vertical}
.ai .row{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.btn{font:600 13px var(--f-body);border-radius:8px;border:1px solid var(--line);background:var(--panel);color:var(--ink);padding:7px 12px;cursor:pointer}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn:disabled{opacity:.5;cursor:default}
.chipq{font:500 12.5px var(--f-body);border:1px dashed var(--line);background:transparent;color:var(--ink-2);border-radius:999px;padding:4px 10px;cursor:pointer}
.answer{white-space:pre-wrap;font-size:14px;line-height:1.55;margin-top:8px}
.n-ok{background:color-mix(in srgb,var(--ok) 16%,transparent);border-bottom:2px solid var(--ok);border-radius:2px}
.n-bad{background:color-mix(in srgb,var(--over) 18%,transparent);border-bottom:2px solid var(--over);border-radius:2px}
.verdict{font-size:13px;margin-top:8px;padding:8px 10px;border-radius:8px;background:var(--chip)}
.foot{margin-top:22px;font-size:13px;color:var(--ink-2);display:grid;gap:6px}
.yrs td,.yrs th{padding:5px 6px}
@media (prefers-reduced-motion:no-preference){circle.pt{transition:r .12s ease,opacity .15s}}
</style>

<div class="wrap">
  <header>
    <div class="kicker">S&amp;P 500 · SEC pay-versus-performance filings · latest 3 fiscal years</div>
    <h1>Do CEOs get paid for returns?</h1>
    <p class="lede" id="lede"></p>
    <div class="facts" id="facts"></div>
  </header>

  <div class="grid">
    <div class="stack">
      <section class="card" aria-labelledby="sc-h">
        <div class="controls">
          <h2 id="sc-h" style="margin-right:auto">Pay vs. 3-year shareholder return</h2>
          <div class="seg" role="group" aria-label="Pay measure">
            <button id="m-sct" aria-pressed="true">Granted pay</button>
            <button id="m-cap" aria-pressed="false">Realised pay (CAP)</button>
          </div>
        </div>
        <div class="controls">
          <select id="sector" aria-label="Sector"><option value="">All sectors</option></select>
          <input type="search" id="q" placeholder="Search ticker, company or CEO" aria-label="Search">
          <label class="tog"><input type="checkbox" id="flagged"> Flagged only</label>
        </div>
        <div class="chart-wrap"><svg id="chart" viewBox="0 0 660 420" role="img" aria-label="Scatter of CEO pay against TSR"></svg><div class="tip" id="tip" hidden></div></div>
        <div class="legend"><span><i style="background:var(--over)"></i>Paid most above model (top 5)</span><span><i style="background:var(--under)"></i>Paid most below model (bottom 5)</span><span><i style="background:var(--muted)"></i>Other companies</span><span>Line: fitted relationship · click a dot to open its dossier</span></div>
      </section>

      <section class="card" aria-labelledby="tb-h">
        <div class="controls"><h2 id="tb-h" style="margin-right:auto">Ranked by pay vs. model</h2><span class="sub" id="count"></span></div>
        <div class="tblwrap"><table><thead><tr>
          <th data-k="t">Company</th><th data-k="s">Sector</th><th class="num" data-k="pay3">Granted 3y avg</th>
          <th class="num" data-k="vs" aria-sort="descending">vs model</th><th class="num" data-k="tsr3">TSR %/yr</th>
          <th class="num" data-k="cap3">Realised 3y avg</th><th class="num" data-k="sopl">Say-on-pay</th><th>Flags</th>
        </tr></thead><tbody id="rows"></tbody></table></div>
      </section>
    </div>

    <aside class="card dossier" id="dossier" aria-live="polite"></aside>
  </div>

  <footer class="foot" id="foot"></footer>
</div>

<script id="data" type="application/json">/*__DATA__*/</script>
<script>
(function(){
const D = JSON.parse(document.getElementById('data').textContent);
const M = D.meta, C = D.companies;
const byT = Object.fromEntries(C.map(c=>[c.t,c]));
const st = {metric:'sct', sector:'', q:'', flagged:false, sel:null, sortK:'vs', sortDir:-1};
try{ const saved = JSON.parse(localStorage.getItem('screener-ui')||'{}'); if(saved.metric) st.metric=saved.metric; }catch(e){}

// ---------- formatting (shared by UI and the AI fact sheet, so numbers match exactly)
const money = v => v==null?'n/a':(Math.abs(v)>=1e9?(v<0?'-':'')+'$'+(Math.abs(v)/1e9).toFixed(1)+'B':(v<0?'-':'')+'$'+(Math.abs(v)/1e6).toFixed(1)+'M');
const pct = (v,d=0,sign=true) => v==null?'n/a':((sign&&v>0?'+':'')+(100*v).toFixed(d)+'%');
const pctRaw = (v,d=0) => v==null?'n/a':((v>0?'+':'')+v.toFixed(d)+'%');
const esc = s => String(s??'').replace(/[&<>"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
const latestSop = c => c.sop.length? c.sop[c.sop.length-1].s : null;
C.forEach(c=>{c.sopl = latestSop(c);});

// ---------- header
document.getElementById('lede').textContent =
  `Boards' pay decisions barely track shareholder returns. The pay CEOs actually realise does, because it is mostly stock. `+
  `Explore ${M.n} S&P 500 companies, see who is paid far above or below what size, sector and returns predict, and check every number back to its SEC filing.`;
const facts = [
  [ (100*M.sct_r2).toFixed(1)+'%', 'of granted pay explained by 3-yr TSR'],
  [ (100*M.cap_r2).toFixed(0)+'%', 'of realised pay (CAP) explained by TSR'],
  [ M.rho_size.toFixed(2)+' vs '+M.rho_tsr.toFixed(2), 'rank correlation of pay with size vs with TSR'],
  [ '+'+M.strategy_ic.A.toFixed(2), 'excess pay vs later returns (no signal)'],
];
document.getElementById('facts').innerHTML = facts.map(f=>`<div class="fact"><b>${f[0]}</b><span>${f[1]}</span></div>`).join('');
const sectors=[...new Set(C.map(c=>c.s))].sort();
document.getElementById('sector').innerHTML += sectors.map(s=>`<option>${esc(s)}</option>`).join('');

// ---------- filters
const visible = c => (!st.sector||c.s===st.sector) && (!st.flagged||c.flags.any) &&
  (!st.q || (c.t+' '+c.n+' '+(c.ceo||'')).toLowerCase().includes(st.q.toLowerCase()));
const top5 = new Set(C.filter(c=>c.rank!=null&&c.rank<=5).map(c=>c.t));
const bot5 = new Set(C.filter(c=>c.rank!=null&&c.rank>=M.n-4).map(c=>c.t));

// ---------- scatter
const W=660,H=420,L=64,R=14,T=14,B=44;
const xMin=-55,xMax=100;
const sx = v => L + (Math.max(xMin,Math.min(xMax,v))-xMin)/(xMax-xMin)*(W-L-R);
const ylog = {min:Math.log10(1), max:Math.log10(150)};
const sym = v => Math.sign(v)*Math.log10(1+Math.abs(v));
const yCap = {min:sym(-60), max:sym(12000)};
function sy(vM){
  if(st.metric==='sct'){ const lv=Math.log10(Math.max(1,vM)); return T+(1-(lv-ylog.min)/(ylog.max-ylog.min))*(H-T-B); }
  const s=sym(vM); return T+(1-(s-yCap.min)/(yCap.max-yCap.min))*(H-T-B);
}
function drawChart(){
  const svg=document.getElementById('chart');
  const ticks = st.metric==='sct'?[1,2,5,10,20,50,100]:[-10,0,10,100,1000,10000];
  let h='';
  ticks.forEach(t=>{const y=sy(t); h+=`<line x1="${L}" x2="${W-R}" y1="${y}" y2="${y}" stroke="var(--grid)"/><text x="${L-8}" y="${y+4}" text-anchor="end">${t<0?'-':''}$${Math.abs(t)>=1000?(Math.abs(t)/1000)+'B':Math.abs(t)+'M'}</text>`;});
  [-40,-20,0,20,40,60,80,100].forEach(t=>{const x=sx(t); h+=`<line x1="${x}" x2="${x}" y1="${T}" y2="${H-B}" stroke="var(--grid)"/><text x="${x}" y="${H-B+16}" text-anchor="middle">${t>0?'+':''}${t}%${t===100?'+':''}</text>`;});
  h+=`<line x1="${sx(0)}" x2="${sx(0)}" y1="${T}" y2="${H-B}" stroke="var(--line)"/>`;
  h+=`<text x="${(L+W-R)/2}" y="${H-6}" text-anchor="middle">annualised TSR, latest 3 fiscal years</text>`;
  // fitted line
  const [b0,b1]=M.fit[st.metric]; const [lo,hi]=M.fit.winsor; let d='';
  for(let i=0;i<=40;i++){const x=lo+(hi-lo)*i/40; const yv= st.metric==='sct'? Math.exp(b0+b1*x)/1e6 : Math.sinh(b0+b1*x); d+=(i?'L':'M')+sx(x).toFixed(1)+','+sy(yv).toFixed(1);}
  h+=`<path d="${d}" fill="none" stroke="var(--ink-2)" stroke-width="2"/>`;
  const pts=C.filter(c=>c.tsr3!=null&&c[st.metric==='sct'?'pay3':'cap3']!=null);
  const order=[...pts].sort((a,b)=>(top5.has(a.t)||bot5.has(a.t))-(top5.has(b.t)||bot5.has(b.t)));
  const labels=[];
  order.forEach(c=>{
    const v=(st.metric==='sct'?c.pay3:c.cap3)/1e6, x=sx(100*c.tsr3), y=sy(v);
    const col= top5.has(c.t)?'var(--over)':bot5.has(c.t)?'var(--under)':'var(--muted)';
    const on=visible(c), sel=c.t===st.sel;
    h+=`<circle class="pt" data-t="${c.t}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${sel?7.5:(top5.has(c.t)||bot5.has(c.t))?5.5:4.2}" fill="${col}" opacity="${on?(top5.has(c.t)||bot5.has(c.t)||sel?1:.6):.12}" stroke="${sel?'var(--ink)':'var(--panel)'}" stroke-width="${sel?2.5:1.2}" tabindex="${on?0:-1}" aria-label="${esc(c.t)}"/>`;
    if((top5.has(c.t)||bot5.has(c.t)||sel)&&on) labels.push({x,y,txt:c.t+(100*c.tsr3>xMax?' ▸':''),sel});
  });
  // greedy label placement: try four spots, keep inside the plot, avoid overlaps
  const fs=parseFloat(getComputedStyle(svg).getPropertyValue('--chart-fs'))||11, cw=fs*0.62, placed=[];
  labels.sort((a,b)=>b.sel-a.sel).forEach(l=>{
    const w=l.txt.length*cw+2, hgt=fs+2;
    const spots=[[8,-7,'start'],[8,fs+6,'start'],[-8,-7,'end'],[-8,fs+6,'end'],[8,-7-fs-2,'start'],[-8,fs*2+8,'end']];
    let best=null;
    for(const [dx,dy,anc] of spots){
      const x0= anc==='start'? l.x+dx : l.x+dx-w, y0=l.y+dy-fs;
      if(x0<L||x0+w>W-R||y0<T||y0+hgt>H-B) continue;
      if(placed.some(p=>x0<p.x+p.w&&x0+w>p.x&&y0<p.y+p.h&&y0+hgt>p.y)) continue;
      best={x0,y0,w,h:hgt,tx:l.x+dx,ty:l.y+dy,anc}; break;
    }
    if(!best){const anc=l.x>W-R-w-10?'end':'start'; best={x0:0,y0:0,w:0,h:0,tx:l.x+(anc==='end'?-8:8),ty:l.y-7,anc};}
    placed.push({x:best.x0,y:best.y0,w:best.w,h:best.h});
    h+=`<text x="${best.tx.toFixed(1)}" y="${best.ty.toFixed(1)}" text-anchor="${best.anc}" style="fill:var(--ink);font-weight:600">${l.txt}</text>`;
  });
  svg.innerHTML=h;
}
const tip=document.getElementById('tip');
document.getElementById('chart').addEventListener('pointerover',e=>{
  const t=e.target.dataset&&e.target.dataset.t; if(!t){tip.hidden=true;return;}
  const c=byT[t], box=e.target.getBoundingClientRect(), wrap=e.currentTarget.parentNode.getBoundingClientRect();
  tip.textContent=`${c.t} · ${money(st.metric==='sct'?c.pay3:c.cap3)} · TSR ${pct(c.tsr3)}/yr`;
  tip.style.left=(box.left-wrap.left+box.width/2)+'px'; tip.style.top=(box.top-wrap.top)+'px'; tip.hidden=false;
});
document.getElementById('chart').addEventListener('pointerout',()=>{tip.hidden=true;});
document.getElementById('chart').addEventListener('click',e=>{const t=e.target.dataset&&e.target.dataset.t; if(t) select(t);});
document.getElementById('chart').addEventListener('keydown',e=>{const t=e.target.dataset&&e.target.dataset.t; if(t&&(e.key==='Enter'||e.key===' ')){e.preventDefault();select(t);}});

// ---------- table
function flagPills(c){
  const p=[];
  if(c.rank!=null&&c.rank<=5)p.push('<span class="pill over">Top-5 above model</span>');
  if(c.rank!=null&&c.rank>=M.n-4)p.push('<span class="pill under">Bottom-5</span>');
  if(c.flags.misaligned)p.push('<span class="pill warn">High pay, weak TSR</span>');
  if(c.flags.low_sop)p.push('<span class="pill warn">Say-on-pay &lt;70%</span>');
  if(c.flags.tsr_issue)p.push('<span class="pill">Proxy TSR error</span>');
  if(c.flags.ceo_change)p.push('<span class="pill">CEO change</span>');
  return p.join(' ');
}
function drawTable(){
  const k=st.sortK, d=st.sortDir;
  const rows=C.filter(visible).sort((a,b)=>{const x=a[k],y=b[k]; if(x==null)return 1; if(y==null)return -1; return (x>y?1:x<y?-1:0)*d;});
  document.getElementById('count').textContent=`${rows.length} of ${C.length} companies`;
  document.getElementById('rows').innerHTML=rows.map(c=>`<tr tabindex="0" data-t="${c.t}" aria-selected="${c.t===st.sel}">
    <td><span class="tk">${c.t}</span> <span class="sub">${esc(c.n.slice(0,26))}</span></td><td class="sub">${esc(c.s)}</td>
    <td class="num">${money(c.pay3)}</td><td class="num" style="color:${c.vs>0?'var(--over)':'var(--under)'}">${c.vs==null?'n/a':pctRaw(c.vs)}</td>
    <td class="num">${pct(c.tsr3)}</td><td class="num">${money(c.cap3)}</td><td class="num">${c.sopl==null?'–':pct(c.sopl,0,false)}</td>
    <td>${flagPills(c)}</td></tr>`).join('');
  document.querySelectorAll('th[data-k]').forEach(th=>{ if(th.dataset.k===k) th.setAttribute('aria-sort',d>0?'ascending':'descending'); else th.removeAttribute('aria-sort'); });
}
document.querySelector('thead').addEventListener('click',e=>{const th=e.target.closest('th[data-k]'); if(!th)return; const k=th.dataset.k; st.sortDir= st.sortK===k? -st.sortDir : (k==='t'||k==='s'?1:-1); st.sortK=k; drawTable();});
document.getElementById('rows').addEventListener('click',e=>{const tr=e.target.closest('tr[data-t]'); if(tr) select(tr.dataset.t);});
document.getElementById('rows').addEventListener('keydown',e=>{const tr=e.target.closest('tr[data-t]'); if(tr&&(e.key==='Enter'||e.key===' ')){e.preventDefault();select(tr.dataset.t);}});

// ---------- dossier
function bar(label,v,max,color){ const w=Math.max(2,Math.min(100,100*v/max)); return `<div class="bar"><span>${label}</span><div class="tr"><div class="fl" style="width:${w}%;background:${color}"></div></div><span class="v">${money(v)}</span></div>`; }
function dossier(c){
  const over=c.vs>0, abs=Math.abs(c.vs||0);
  const status = c.vs==null?'<span class="pill">No 3-yr window</span>': abs<25?`<span class="pill">In line with model (${pctRaw(c.vs)})</span>`:`<span class="pill ${over?'over':'under'}">Paid ${over?'above':'below'} model ${pctRaw(c.vs)}</span>`;
  const maxPay=Math.max(c.pay3||0,c.pred||0,1);
  const yrs=c.years.map(y=>`<tr><td>FY${y.fy}${y.peos>1?' *':''}</td><td class="num">${money(y.sct)}</td><td class="num">${money(y.cap)}</td><td class="num">${pct(y.tsr)}</td></tr>`).join('');
  const mixParts = c.mix?[['Salary',c.mix.salary,'--mix1'],['Cash incentive',c.mix.cash,'--mix2'],['Stock',c.mix.stock,'--mix3'],['Options',c.mix.option,'--mix4'],['Other',c.mix.other,'--mix5']]:[];
  const mix = c.mix? `<div class="mixbar" role="img" aria-label="Pay mix">${mixParts.filter(p=>p[1]>0.004).map(p=>`<span title="${p[0]} ${pct(p[1],0,false)}" style="width:${100*p[1]}%;background:var(${p[2]})"></span>`).join('')}</div>
     <div class="legend">${mixParts.map(p=>`<span><i style="background:var(${p[2]})"></i>${p[0]} ${pct(p[1],0,false)}</span>`).join('')}</div>`:'<p class="sub">Not available</p>';
  const sop = c.sop.length? c.sop.map(s=>`<span class="pill ${s.s<0.5?'over':s.s<0.7?'warn':'ok'}">${s.d.slice(0,4)}: ${pct(s.s,0,false)}</span>`).join(' ') : '<span class="sub">Not parsed for this company</span>';
  const ch=c.checks, checks=[
    [ch.pay_in_proxy,`XBRL granted pay (${money(c.years.at(-1).sct)}) appears verbatim in the proxy text`],
    [ch.cap_in_proxy,`XBRL realised pay (${money(c.years.at(-1).cap)}) appears verbatim in the proxy text`],
    [ch.mix_years>0,`Pay mix reconciled to the XBRL total in ${ch.mix_years||0} year(s)`],
    [ch.tsr_gap!=null && !c.flags.tsr_issue, ch.tsr_gap==null?'Proxy TSR not available to cross-check':`Proxy TSR vs our market-data TSR: max gap ${ch.tsr_gap.toFixed(2)} pts${c.flags.tsr_issue?' ('+c.flags.tsr_issue.replace('_',' ')+' filing error)':''}`],
  ].map(([ok,txt])=>`<li><span class="ic ${ok?'ok':'warn'}">${ok?'✓':'!'}</span><span>${esc(txt)}</span></li>`).join('');
  const alt=c.alt? `Rank under alternative models: no sector controls #${c.alt.nofe??'–'}, 5-yr window #${c.alt.w5??'–'}, excluding no-grant CEOs #${c.alt.exnoeq??'–'}.`:'';
  const strat = c.strat&&c.strat.B? `In Sept-2025 its excess-pay quintile was ${esc(c.strat.B.q)}; CAPM abnormal return since: ${pct(c.strat.B.ar)}.`:'';
  const note = c.note? `<div class="sec"><h3>Case study</h3><div class="note"><b>${esc(c.note.verdict)}</b>${esc(c.note.text)}<div class="sub" style="margin-top:6px">Sources: ${c.note.sources.map(s=>`<a href="${s.url}" target="_blank" rel="noopener">${esc(s.label)}</a>`).join(' · ')}</div></div></div>`:'';
  return `<div class="dhead"><div><div class="kicker">${esc(c.s)} · FY${c.fy}</div><div class="name">${esc(c.n)} <span class="tk">${c.t}</span></div><div class="sub">CEO: ${esc(c.ceo||'not tagged')}${c.flags.ceo_change?' · CEO change in window':''}${c.flags.co_ceo?' · co-CEOs':''}</div></div><div>${status}${c.rank?`<div class="sub" style="text-align:right;margin-top:4px">rank ${c.rank} of ${M.n}</div>`:''}</div></div>
    <div class="sec" style="border:0;margin-top:10px;padding-top:0"><h3>Granted pay vs. model (3-yr average)</h3><div class="bars">${c.pay3!=null?bar('Actual',c.pay3,maxPay,over?'var(--over)':'var(--under)'):''}${c.pred!=null?bar('Predicted',c.pred,maxPay,'var(--muted)'):''}</div><div class="sub">Predicted from TSR, start-of-window market cap and sector (model R² ${(100*M.model_r2).toFixed(0)}%). ${alt}</div></div>
    <div class="kv"><div><b>${pct(c.tsr3)}</b><span>TSR per year, 3 yrs</span></div><div><b>${money(c.cap3)}</b><span>Realised pay (CAP), 3-yr avg</span></div>
      <div><b>${money(c.mcap)}</b><span>Market cap today</span></div><div><b>${c.sopl==null?'–':pct(c.sopl,0,false)}</b><span>Latest say-on-pay support</span></div></div>
    <div class="sec"><h3>Pay by fiscal year (Item 402(v) table)</h3><div style="overflow-x:auto"><table class="yrs"><thead><tr><th>Year</th><th class="num">Granted</th><th class="num">Realised</th><th class="num">TSR</th></tr></thead><tbody>${yrs}</tbody></table></div><div class="sub">* more than one CEO that year; the year-end CEO is shown.</div></div>
    <div class="sec"><h3>Pay mix, latest 3 years</h3>${mix}</div>
    <div class="sec"><h3>Say-on-pay votes</h3>${sop}</div>
    ${note}
    <div class="sec"><h3>Data checks</h3><ul class="checks">${checks}</ul><div class="sub" style="margin-top:6px">${strat} <a href="${c.url}" target="_blank" rel="noopener">Open the SEC proxy filing</a></div></div>
    <div class="sec ai" id="ai"><h3>Ask the AI analyst</h3>
      <p class="sub" id="ai-status">Connecting to Claude…</p>
      <div id="ai-ui" hidden>
        <div class="row">${['Why is pay above or below the model here?','Is this CEO\'s pay aligned with shareholder returns?','What should a shareholder ask the board?'].map(q=>`<button class="chipq" type="button">${q}</button>`).join('')}</div>
        <textarea id="ai-q" aria-label="Your question">Is this CEO's pay aligned with shareholder returns?</textarea>
        <div class="row"><button class="btn primary" id="ai-go" type="button">Ask</button><button class="btn" id="ai-stop" type="button" hidden>Stop</button></div>
        <div class="answer" id="ai-out"></div><div class="verdict" id="ai-check" hidden></div>
        <p class="sub">Claude sees only this company's verified data shown above. Every figure in its answer is checked against that data: <span class="n-ok">green</span> = matched, <span class="n-bad">red</span> = not found, so don't rely on it.</p>
      </div></div>`;
}

// ---------- AI analyst (grounded + automatic number check)
let sampleFn=null, ctl=null;
function factSheet(c){
  const lines=[
    `Company: ${c.n} (${c.t}), sector ${c.s}, CEO ${c.ceo||'not tagged'}, latest fiscal year FY${c.fy}.`,
    `Granted pay (Summary Compensation Table), 3-year average: ${money(c.pay3)}. Model prediction: ${money(c.pred)}. Pay vs model: ${c.vs==null?'n/a':pctRaw(c.vs)}. Rank ${c.rank} of ${M.n} (1 = furthest above model).`,
    `Realised pay (compensation actually paid, CAP), 3-year average: ${money(c.cap3)}.`,
    `Total shareholder return: ${pct(c.tsr3)} per year over 3 years; ${pct(c.tsr1)} over 1 year; peer group 3-year cumulative ${pct(c.peer3)}.`,
    `Market cap today: ${money(c.mcap)}.`,
    `By fiscal year: `+c.years.map(y=>`FY${y.fy}: granted ${money(y.sct)}, realised ${money(y.cap)}, TSR ${pct(y.tsr)}${y.peos>1?', '+y.peos+' CEOs that year':''}`).join('; ')+'.',
    c.mix?`Pay mix over the last ${c.mix.years} years: salary ${pct(c.mix.salary,0,false)}, cash incentive ${pct(c.mix.cash,0,false)}, stock ${pct(c.mix.stock,0,false)}, options ${pct(c.mix.option,0,false)}, other ${pct(c.mix.other,0,false)}.`:'Pay mix: not available.',
    c.sop.length?`Say-on-pay support: `+c.sop.map(s=>`${s.d.slice(0,4)} ${pct(s.s,0,false)}`).join(', ')+'.':'Say-on-pay: not parsed.',
    `Flags: ${[c.flags.ceo_change&&'CEO change within the window',c.flags.co_ceo&&'co-CEOs',c.flags.misaligned&&'above-model pay with below-median TSR',c.flags.low_sop&&'say-on-pay below 70%',c.flags.tsr_issue&&('proxy TSR filing error: '+c.flags.tsr_issue)].filter(Boolean).join('; ')||'none'}.`,
    c.note?`Verified case-study note (from the SEC filing): ${c.note.verdict}. ${c.note.text}`:`No qualitative research is available for this company.`,
    `Sample context (${M.n} S&P 500 companies): median granted pay ${money(M.median_pay3)}; median TSR ${pct(M.median_tsr3)} per year; TSR explains ${(100*M.sct_r2).toFixed(1)}% of granted pay and ${(100*M.cap_r2).toFixed(0)}% of realised pay.`,
  ];
  return lines.join('\n');
}
function prompt(c,q){
  return `You are an equity analyst explaining CEO pay to an investor, inside a screener.\n\nRULES\n`+
  `1. Use ONLY the DATA below. Do not use outside knowledge, and do not calculate new numbers.\n`+
  `2. Every number you write must be copied exactly from the DATA, with the same rounding and units (for example $61.4M, +244%).\n`+
  `3. If the DATA cannot answer the question, say so plainly.\n`+
  `4. Keep "granted pay" (what the board awarded) separate from "realised pay" (CAP, which moves with the stock price).\n`+
  `5. "Pay vs model" compares pay with what size, sector and TSR predict; it is not a verdict on fairness by itself.\n`+
  `6. Plain prose, at most 150 words, then one line starting "What to check next:".\n\nDATA\n${factSheet(c)}\n\nQUESTION\n${q}`;
}
const NUM=/[−-]?\$?\d[\d,]*(?:\.\d+)?\s?(?:%|pp|B\b|M\b|bn\b|billion\b|million\b|x\b)?/g;
function parseNum(tok){
  const t=tok.replace('−','-').replace(/,/g,'').trim(); let v=parseFloat(t.replace(/[^0-9.\-]/g,''));
  let kind=/%|pp/.test(t)?'pct':/\$/.test(t)||/[MB]$|bn|billion|million/.test(t)?'money':'plain';
  if(/B$|bn|billion/.test(t)) v*=1000;  // money in $M
  return {v:Math.abs(v),kind};
}
function allowedFrom(text){ const a=[]; (text.match(NUM)||[]).forEach(t=>a.push(parseNum(t))); return a; }
function checkAnswer(ans,allowed){
  let ok=0,bad=0; const html=esc(ans).replace(NUM,tok=>{
    const p=parseNum(tok.replace(/&amp;/g,'&'));
    if(p.kind==='plain' && p.v<=12 && Number.isInteger(p.v)) return tok;          // small counts ("3 years") are not checked
    const hit=allowed.some(a=>(a.kind===p.kind||p.kind==='plain'||a.kind==='plain') && Math.abs(a.v-p.v)<=Math.max(0.051,0.005*a.v));
    hit?ok++:bad++; return `<span class="${hit?'n-ok':'n-bad'}">${tok}</span>`;
  });
  return {html,ok,bad};
}
function wireAI(c){
  const status=document.getElementById('ai-status'), ui=document.getElementById('ai-ui');
  if(sampleFn===null){ status.textContent='The AI analyst runs when this page is opened in Claude. Everything else works offline.'; return; }
  if(sampleFn===undefined){ status.textContent='Connecting to Claude…'; return; }
  status.hidden=true; ui.hidden=false;
  const q=document.getElementById('ai-q'), go=document.getElementById('ai-go'), stop=document.getElementById('ai-stop'),
        out=document.getElementById('ai-out'), chk=document.getElementById('ai-check');
  document.querySelectorAll('.chipq').forEach(b=>b.onclick=()=>{q.value=b.textContent; go.click();});
  stop.onclick=()=>ctl&&ctl.abort();
  go.onclick=async()=>{
    const question=q.value.trim(); if(!question) return;
    ctl=new AbortController(); go.disabled=true; stop.hidden=false; chk.hidden=true; out.textContent='Thinking…';
    const sheet=factSheet(c), allowed=allowedFrom(sheet);
    try{
      const {text}=await sampleFn(prompt(c,question),{signal:ctl.signal,onText:({text})=>{out.textContent=text;}});
      const r=checkAnswer(text,allowed); out.innerHTML=r.html; chk.hidden=false;
      chk.innerHTML = r.bad===0 ? `<span class="ic ok">✓</span> Fact check: all ${r.ok} figure${r.ok===1?'':'s'} in this answer match the verified data.`
                              : `<span class="ic warn">!</span> Fact check: ${r.bad} of ${r.ok+r.bad} figures could not be matched to the verified data (red). Treat them as unreliable.`;
    }catch(e){
      out.textContent=e&&e.text?e.text:'';
      const msg={not_granted:'Claude access was not allowed for this page.',sampling_disabled:'Claude is not available for this account.',rate_limited:'Too many requests right now. Try again in a minute.',refused:'Claude declined this question. Try rephrasing it.',cancelled:''}[e&&e.code];
      chk.hidden=!(msg??true); chk.textContent= msg ?? 'Something went wrong reaching Claude. Try again.';
      if(e&&(e.code==='not_granted'||e.code==='sampling_disabled')){ document.getElementById('ai-ui').hidden=true; status.hidden=false; status.textContent=msg; sampleFn=null; }
    }finally{ go.disabled=false; stop.hidden=true; }
  };
}

// ---------- footer
const V=M.validation;
document.getElementById('foot').innerHTML=`
  <div><b>How we know the numbers are right.</b> Every CEO pay figure comes from SEC pay-versus-performance XBRL and appears verbatim in the human-readable proxy (${V.source_match} companies). Pay-mix rows reconcile to those totals (${V.mix}). TSR is rebuilt independently from prices with dividends reinvested (median gap to proxies ${V.tsr_median_gap.toFixed(2)} pts). Case-study facts are found in the cited filings (${V.claims}). A permutation test confirms that granted pay is unrelated to TSR (p = ${V.perm_p_sct.toFixed(2)}).</div>
  <div>Pay is the year-end CEO's. Granted = Summary Compensation Table total; realised = compensation actually paid (CAP). The model is ln(granted pay) ~ TSR + ln(start-of-window market cap) + sector, with ${M.n} companies. Associations, not causation; today's index members only (survivorship bias). <a href="${M.repo}" target="_blank" rel="noopener">Code, data and full report</a>.</div>`;

// ---------- state + events
function select(t,user=true){ st.sel=t; drawChart(); drawTable(); const c=byT[t]; const d=document.getElementById('dossier'); d.innerHTML=dossier(c); wireAI(c);
  if(user && matchMedia('(max-width:980px)').matches) d.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth', block:'start'}); }
function setMetric(m){ st.metric=m; document.getElementById('m-sct').setAttribute('aria-pressed',m==='sct'); document.getElementById('m-cap').setAttribute('aria-pressed',m==='cap'); try{localStorage.setItem('screener-ui',JSON.stringify({metric:m}));}catch(e){} drawChart(); }
document.getElementById('m-sct').onclick=()=>setMetric('sct');
document.getElementById('m-cap').onclick=()=>setMetric('cap');
document.getElementById('sector').onchange=e=>{st.sector=e.target.value; drawChart(); drawTable();};
document.getElementById('q').oninput=e=>{st.q=e.target.value; drawChart(); drawTable();};
document.getElementById('flagged').onchange=e=>{st.flagged=e.target.checked; drawChart(); drawTable();};
setMetric(st.metric);
select(C.slice().sort((a,b)=>(a.rank??999)-(b.rank??999))[0].t,false);
const use = window.claude && window.claude.use ? window.claude.use('sample') : Promise.resolve(null);
use.then(s=>{ sampleFn=s||null; if(st.sel) wireAI(byT[st.sel]); }).catch(()=>{ sampleFn=null; if(st.sel) wireAI(byT[st.sel]); });
})();
</script>
"""


if __name__ == "__main__":
    build()
