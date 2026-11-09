"""Replication: do the 100-company findings hold on the full S&P 500?

    python -m src.replication      (after both scopes have been run)

Reads output/results.json (sample) and output/full_universe/results.json
(full index) and writes output/replication.json plus chart
output/charts/09_replication.png. Every number is read from the two results
files, never typed.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config


def _load(out_dir, proc_dir) -> dict | None:
    p = out_dir / "results.json"
    if not p.exists():
        return None
    r = json.loads(p.read_text())
    v = out_dir / "validation" / "validation.json"
    r["_validation"] = json.loads(v.read_text()) if v.exists() else {}
    st = proc_dir / "edgar_status.csv"
    r["_status"] = pd.read_csv(st) if st.exists() else None
    return r


def summary(r: dict) -> dict:
    R, C = r["regressions"], r["correlations"]["3y"]
    st, v = r["_status"], r["_validation"]
    s3, c3 = R["sct_3y_3_size_sector"], R["cap_3y_3_size_sector"]
    xn = R["robustness_3y"]["excl_no_equity_grants"]
    pct = lambda b: 100 * (np.exp(10 * b) - 1)  # noqa: E731
    out = {
        "n_universe": int(len(st)) if st is not None else None,
        "n_pvp_xbrl": int((st["pvp_source"] == "xbrl").sum()) if st is not None else None,
        "n_sct_matched": int((st["n_sct_matched"] > 0).sum()) if st is not None else None,
        "n_model_3y": s3["n"],
        "sct_r2_simple": R["sct_3y_1_simple"]["r2"], "cap_r2_simple": R["cap_3y_1_simple"]["r2"],
        "sct_effect": s3["pct_pay_per_10pp_tsr"], "sct_p": s3["coefs"]["tsr_pp_w"]["p"],
        "sct_ci": [pct(s3["coefs"]["tsr_pp_w"]["ci_lo"]), pct(s3["coefs"]["tsr_pp_w"]["ci_hi"])],
        "cap_effect": c3["pct_pay_per_10pp_tsr"], "cap_p": c3["coefs"]["tsr_pp_w"]["p"],
        "cap_ci": [pct(c3["coefs"]["tsr_pp_w"]["ci_lo"]), pct(c3["coefs"]["tsr_pp_w"]["ci_hi"])],
        "rho_size": C["sct_vs_mcap"]["spearman_rho"], "rho_tsr": C["sct_vs_tsr"]["spearman_rho"],
        "rho_tsr_p": C["sct_vs_tsr"]["spearman_p"],
        "size_elasticity": s3.get("size_elasticity"), "size_p": s3["coefs"]["ln_mcap"]["p"],
        "sct_5y_effect": R["sct_5y_3_size_sector"]["pct_pay_per_10pp_tsr"],
        "sct_5y_p": R["sct_5y_3_size_sector"]["coefs"]["tsr_pp_w"]["p"],
        "excl_no_equity_n_excluded": len(xn.get("excluded", [])),
        "excl_no_equity_effect": xn["pct_pay_per_10pp_tsr"], "excl_no_equity_p": xn["coefs"]["tsr_pp_w"]["p"],
        "panel_sct_p": r["panel"]["sct_same_year"]["p"], "panel_cap_effect": r["panel"]["cap_same_year"]["pct_pay_per_10pp_tsr"],
        "sop_rho": r["say_on_pay"]["corr_resid_support"]["spearman_rho"],
        "sop_p": r["say_on_pay"]["corr_resid_support"]["spearman_p"],
        "sop_meetings": r["say_on_pay"]["n_meetings"], "sop_failed": r["say_on_pay"]["n_failed_votes"],
        "tsr_flagged": r["tsr_quality"]["n_companies_flagged"], "tsr_median_gap": r["tsr_quality"]["median_abs_gap_pts"],
        "top_overpaid": [o["ticker"] for o in r["outliers"]["overpaid"]],
        "top_underpaid": [o["ticker"] for o in r["outliers"]["underpaid"]],
    }
    if "strategy" in r:
        for k, c in r["strategy"]["cohorts"].items():
            m = c["measures"]["capm_abnormal"]
            out[f"strategy_{k}_n"] = c["n"]
            out[f"strategy_{k}_ic"] = m["rank_ic"]["spearman_rho"]
            out[f"strategy_{k}_ic_p"] = m["rank_ic"]["spearman_p"]
    if "backtest" in r:
        ls = r["backtest"]["portfolios"]["Long underpaid / short overpaid"]
        out.update({"bt_alpha": ls["alpha_ann"], "bt_alpha_t": ls["alpha_t"], "bt_sharpe": ls["sharpe"],
                    "bt_beta": ls["beta"], "bt_n_per_fifth": r["backtest"]["n_per_quintile"]["Q1 most underpaid"]})
    if v:
        out["val_source_match"] = f"{v['source_match']['sct_found']}/{v['source_match']['n']}"
        out["val_mix"] = f"{v['mix_reconciliation']['xbrl_match_pass']}/{v['mix_reconciliation']['rows']}"
        out["val_perm_p_sct"] = v["permutation"]["sct"]["perm_p_two_sided"]
        if "sop_crosscheck" in v:
            out["val_sop_agree"] = f"{v['sop_crosscheck']['n_agree']}/{v['sop_crosscheck']['n_compared']}"
    return out


def chart(s: dict, f: dict) -> None:
    from . import charts as ch
    ch._style()
    plt = ch.plt
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), gridspec_kw={"wspace": 0.35})
    lab = [f"Sample (n={s['n_model_3y']})", f"Full index (n={f['n_model_3y']})"]
    cols = [ch.CONTEXT, ch.BLUE]
    # 1. R2 granted vs realised
    ax = axes[0]
    x = np.arange(2)
    for i, (d, c) in enumerate(((s, cols[0]), (f, cols[1]))):
        vals = [100 * d["sct_r2_simple"], 100 * d["cap_r2_simple"]]
        ax.bar(x + (i - 0.5) * 0.36, vals, width=0.34, color=c, edgecolor=ch.SURFACE, linewidth=2, label=lab[i])
        for xi, vv in zip(x + (i - 0.5) * 0.36, vals):
            ax.text(xi, vv + 1, f"{vv:.1f}%" if vv < 10 else f"{vv:.0f}%", ha="center", fontsize=9, color=ch.INK_2)
    ax.set_xticks(x, ["Granted pay", "Realised pay"])
    ax.set_title("Share of pay explained by TSR (R²)")
    ax.yaxis.set_major_formatter(ch.mticker.PercentFormatter(decimals=0))
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left")
    # 2. Effect with CI
    ax = axes[1]
    for i, (d, c) in enumerate(((s, cols[0]), (f, cols[1]))):
        for j, (eff, ci) in enumerate(((d["sct_effect"], d["sct_ci"]),)):
            ax.errorbar([i], [eff], yerr=[[eff - ci[0]], [ci[1] - eff]], fmt="o", color=c if i else ch.INK_2,
                        ecolor=c if i else ch.MUTED, elinewidth=2.5, capsize=6, markersize=9)
            ax.text(i + 0.08, eff, f" {eff:+.1f}%", va="center", fontsize=9.5, color=ch.INK_2)
    ax.axhline(0, color=ch.AXIS, lw=1)
    ax.set_xticks([0, 1], ["Sample", "Full index"])
    ax.set_xlim(-0.5, 1.6)
    ax.set_title("Granted pay per +10 pts TSR (95% CI)")
    ax.yaxis.set_major_locator(ch.mticker.MultipleLocator(5))
    ax.yaxis.set_major_formatter(ch.mticker.FuncFormatter(lambda v, _: f"{v:+.0f}%" if v else "0"))
    ax.grid(axis="x", visible=False)
    # 3. Rank correlations
    ax = axes[2]
    for i, (d, c) in enumerate(((s, cols[0]), (f, cols[1]))):
        vals = [d["rho_size"], d["rho_tsr"]]
        ax.bar(x + (i - 0.5) * 0.36, vals, width=0.34, color=c, edgecolor=ch.SURFACE, linewidth=2)
        for xi, vv in zip(x + (i - 0.5) * 0.36, vals):
            ax.text(xi, vv + 0.015, f"{vv:.2f}", ha="center", fontsize=9, color=ch.INK_2)
    ax.set_xticks(x, ["with company size", "with 3-yr TSR"])
    ax.set_title("Rank correlation of granted pay")
    ax.grid(axis="x", visible=False)
    holds = f["sct_r2_simple"] < 0.05 and f["cap_r2_simple"] > 0.3
    title = ("The pattern holds on the full S&P 500: TSR explains little of granted pay, much of realised pay"
             if holds else "Sample vs full S&P 500")
    fig.suptitle(title, x=0.01, ha="left", fontsize=15, fontweight="semibold", y=1.07)
    fig.text(0.01, 0.995, f"Same pipeline, same model: the 100-company stratified sample vs every S&P 500 company with data "
                          f"({f['n_pvp_xbrl']} of {f['n_universe']} have pay-versus-performance XBRL).",
             fontsize=10, color=ch.INK_2, ha="left")
    ch._footer(fig, ch.SOURCE.replace("100-company sector-stratified S&P 500 sample.", "Sample and full S&P 500."), y=-0.05)
    ch._save(fig, "09_replication.png")


def run() -> dict | None:
    s = _load(config.OUTPUT_SAMPLE, config.DATA_PROCESSED_SAMPLE)
    f = _load(config.OUTPUT_FULL, config.DATA_PROCESSED_FULL)
    if not s or not f:
        print("[replication] full-universe results not found; run FULL_UNIVERSE=1 python -m src.pipeline first")
        return None
    out = {"sample": summary(s), "full": summary(f)}
    # Validate the full index's size measure (SEC shares x price) against
    # Yahoo's market cap on the sample, where both exist.
    fun = pd.read_csv(config.DATA_PROCESSED_SAMPLE / "fundamentals.csv").dropna(subset=["mcap_now_yahoo", "mcap_now_sec"])
    ld = np.log(fun["mcap_now_sec"] / fun["mcap_now_yahoo"])
    out["size_check"] = {"n": int(len(fun)), "within_10pct": int((ld.abs() < np.log(1.1)).sum()),
                         "corr_log": float(np.corrcoef(np.log(fun["mcap_now_sec"]), np.log(fun["mcap_now_yahoo"]))[0, 1]),
                         "outside": fun.loc[ld.abs() >= np.log(1.1), "ticker"].tolist()}
    out["full"]["top_overpaid_in_sample"] = [t for t in out["full"]["top_overpaid"] if t in set(s["_status"]["ticker"])]
    (config.OUTPUT_SAMPLE / "replication.json").write_text(json.dumps(out, indent=2, default=float))
    chart(out["sample"], out["full"])
    a, b = out["sample"], out["full"]
    print(f"[replication] granted R2 {100 * a['sct_r2_simple']:.1f}% vs {100 * b['sct_r2_simple']:.1f}%; "
          f"effect {a['sct_effect']:+.1f}% (p={a['sct_p']:.2f}) vs {b['sct_effect']:+.1f}% (p={b['sct_p']:.2f}); "
          f"CAP R2 {100 * a['cap_r2_simple']:.0f}% vs {100 * b['cap_r2_simple']:.0f}%; "
          f"rho size {a['rho_size']:.2f} vs {b['rho_size']:.2f}, rho TSR {a['rho_tsr']:.2f} vs {b['rho_tsr']:.2f}")
    return out


if __name__ == "__main__":
    run()
