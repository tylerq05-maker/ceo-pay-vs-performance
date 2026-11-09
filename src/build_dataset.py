"""Phase 4a - Merge everything into tidy analysis datasets.

* ``data/processed/master.csv``       - one row per company (cross-section)
* ``data/processed/master_panel.csv`` - one row per company x fiscal year
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .pvp_xbrl import same_person
from .sct_parser import COMPONENTS


def _ceo_changed(g: pd.DataFrame) -> bool:
    """True if a multi-PEO year occurs or the incumbent changes within ``g``."""
    if g["multi_peo_year"].fillna(False).astype(bool).any():
        return True
    names = [n for n in g.sort_values("fy")["ceo_name"] if isinstance(n, str) and n]
    return any(not same_person(a, b) for a, b in zip(names, names[1:]))


def build_panel(pvp: pd.DataFrame, fis: pd.DataFrame) -> pd.DataFrame:
    panel = pvp.merge(fis[["ticker", "fy", "indep_tsr_value", "discrepancy_flag", "discrepancy_reason"]],
                      on=["ticker", "fy"], how="left")
    panel = panel.sort_values(["ticker", "fy"])
    prev = panel.groupby("ticker")["indep_tsr_value"].shift(1).fillna(100.0)
    panel["indep_tsr_annual"] = panel["indep_tsr_value"] / prev - 1
    panel["proxy_tsr_annual"] = panel["tsr_annual"]
    return panel


def window_pay(pvp: pd.DataFrame, n: int) -> pd.DataFrame:
    rows = []
    for tk, g in pvp.groupby("ticker"):
        g = g.sort_values("fy").tail(n)
        if len(g) < n:
            continue
        rows.append({
            "ticker": tk,
            f"sct_avg_{n}y": g["ceo_sct_total"].mean(),
            f"cap_avg_{n}y": g["ceo_cap"].mean(),
            f"seat_sct_avg_{n}y": g["seat_sct_total"].fillna(g["ceo_sct_total"]).mean(),
            f"nonpeo_sct_avg_{n}y": g["nonpeo_avg_sct"].mean(),
            f"ceo_change_{n}y": _ceo_changed(g),
            f"multi_peo_years_{n}y": int(g["multi_peo_year"].fillna(False).astype(bool).sum()),
        })
    return pd.DataFrame(rows)


def pay_mix(sct: pd.DataFrame, pvp: pd.DataFrame, n: int = config.PRIMARY_WINDOW_YEARS) -> pd.DataFrame:
    """Share of SCT pay by component over the last ``n`` fiscal years (only
    reconciled CEO rows; years without a reconciled row are skipped)."""
    latest = pvp.groupby("ticker")["fy"].max()
    s = sct.merge(latest.rename("latest_fy"), left_on="ticker", right_index=True)
    s = s[s["fy"] > s["latest_fy"] - n]
    agg = s.groupby("ticker")[COMPONENTS + ["sct_total"]].sum()
    out = pd.DataFrame(index=agg.index)
    tot = agg["sct_total"]
    for c in COMPONENTS:
        out[f"mix_{c}"] = agg[c] / tot
    out["mix_equity"] = (agg["stock"] + agg["option"]) / tot
    out["mix_cash_incentive"] = (agg["bonus"] + agg["neip"]) / tot
    out["mix_fixed_other"] = (agg["salary"] + agg["pension"] + agg["other"]) / tot
    out["mix_years"] = s.groupby("ticker").size()
    out["uses_options"] = agg["option"] > 0
    return out.reset_index()


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    P = config.DATA_PROCESSED
    sample = pd.read_csv(P / "sample.csv")
    pvp = pd.read_csv(P / "pvp_company_years.csv")
    sct = pd.read_csv(P / "sct_ceo_rows.csv")
    fis = pd.read_csv(P / "tsr_fiscal.csv")
    win = pd.read_csv(P / "tsr_windows.csv")
    fun = pd.read_csv(P / "fundamentals.csv")
    xc = pd.read_csv(P / "tsr_crosscheck.csv")
    st = pd.read_csv(P / "edgar_status.csv")

    panel = build_panel(pvp, fis)
    panel = panel.merge(sample[["ticker", "company", "sector"]], on="ticker", how="left")

    latest = (pvp.sort_values("fy").groupby("ticker").tail(1)
              .set_index("ticker")[["ceo_name", "ceo_sct_total", "ceo_cap", "n_peos"]]
              .rename(columns={"ceo_name": "ceo_name_latest", "ceo_sct_total": "sct_latest",
                               "ceo_cap": "cap_latest", "n_peos": "n_peos_latest"}))

    m = sample[["ticker", "company", "sector", "sub_industry", "cik", "hq", "founded"]].copy()
    m = m.merge(st[["ticker", "accession", "filing_date", "proxy_url", "n_pvp_years", "n_sct_matched"]],
                on="ticker", how="left")
    m = m.merge(latest, left_on="ticker", right_index=True, how="left")
    for n in config.WINDOWS:
        m = m.merge(window_pay(pvp, n), on="ticker", how="left")
    m = m.merge(win, on="ticker", how="left")
    m = m.merge(fun, on="ticker", how="left")
    m = m.merge(pay_mix(sct, pvp), on="ticker", how="left")
    m = m.merge(xc[["ticker", "tsr_discrepancy", "reasons", "max_abs_diff_pts"]]
                .rename(columns={"reasons": "tsr_discrepancy_reason",
                                 "max_abs_diff_pts": "tsr_max_gap_pts"}), on="ticker", how="left")

    # Derived variables -----------------------------------------------------
    for n in config.WINDOWS:
        m[f"ln_sct_avg_{n}y"] = np.log(m[f"sct_avg_{n}y"])
        m[f"ln_mcap_start_{n}y"] = np.log(m[f"mcap_start_{n}y"])
        m[f"rel_tsr_{n}y"] = m[f"tsr_{n}y"] - m[f"peer_tsr_{n}y"]
        m[f"cap_to_sct_{n}y"] = m[f"cap_avg_{n}y"] / m[f"sct_avg_{n}y"]
    m["ln_mcap_now"] = np.log(m["mcap_now"])
    m["co_ceo"] = m["ticker"].map(
        pvp.groupby("ticker")["multi_peo_year"].apply(lambda s: s.fillna(False).astype(bool).sum() >= 3))

    m = m.sort_values(["sector", "ticker"]).reset_index(drop=True)
    m.to_csv(P / "master.csv", index=False)
    panel.to_csv(P / "master_panel.csv", index=False)
    print(f"[build] master.csv: {len(m)} companies x {m.shape[1]} columns; "
          f"panel: {len(panel)} company-years")
    return m, panel


if __name__ == "__main__":
    build()
