"""Phase 2 orchestrator - CEO pay for every company in the sample.

For each company:
1. Walk its DEF 14A filings newest-first (since 2023, when PvP began) and use
   the first one whose XBRL contains ``ecd:PeoTotalCompAmt``. Special-meeting
   proxies without a PvP table are skipped automatically.
2. Parse the PvP facts (``pvp_xbrl``) and the Summary Compensation Table from
   the same filing's HTML (``sct_parser``); SCT rows are linked to fiscal years
   by matching their Total to the XBRL PEO total.
3. If no filing carries PvP XBRL, fall back to the SCT alone (first-listed
   executive = PEO) so that at least reported pay is available.

Outputs (data/processed):
* ``pvp_company_years.csv`` - one row per company x fiscal year
* ``pvp_peo_rows.csv``      - every PEO reported (multi-CEO years show >1 row)
* ``sct_ceo_rows.csv``      - reconciled SCT component rows for the CEO
* ``edgar_status.csv``      - which filing was used, and what was found
"""
from __future__ import annotations

import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from . import config, edgar, http_cache, pvp_xbrl, sct_parser

MIN_PROXY_DATE = "2023-01-01"
MAX_PROXIES_TO_TRY = 4


def _pvp_from_filing(f: edgar.Filing):
    if not (f.is_xbrl or f.is_ixbrl):
        return None
    name = edgar.xbrl_instance_name(f)
    if not name:
        return None
    xml = http_cache.get(f.url(name), binary=True)
    if not xml or b"PeoTotalCompAmt" not in xml:
        return None
    co, peo = pvp_xbrl.build_tables(pvp_xbrl.parse_instance(xml))
    if co.empty:
        return None
    return co, peo, name


def process_company(row: pd.Series) -> dict:
    cik, ticker = int(row["cik"]), row["ticker"]
    status = {"ticker": ticker, "cik": cik, "pvp_source": None, "accession": None,
              "filing_date": None, "proxy_url": None, "n_pvp_years": 0,
              "n_sct_matched": 0, "error": None}
    out = {"status": status, "years": pd.DataFrame(), "peo": pd.DataFrame(), "sct": pd.DataFrame()}
    try:
        proxies = [p for p in edgar.proxy_filings(cik) if p.filing_date >= MIN_PROXY_DATE]
        chosen = None
        for f in proxies[:MAX_PROXIES_TO_TRY]:
            res = _pvp_from_filing(f)
            if res is not None:
                chosen = (f, *res)
                break
        if chosen:
            f, co, peo, inst_name = chosen
            html = edgar.primary_html(f) or ""
            rows = sct_parser.parse_sct(html)
            # Names are sometimes untagged in single-CEO years; recover them
            # from the reconciled SCT rows before choosing year-end incumbents.
            peo = pvp_xbrl.backfill_names(peo, {r.total: r.name for r in rows})
            years = pvp_xbrl.company_year_table(co, peo)
            status.update(pvp_source="xbrl", accession=f.accession, filing_date=f.filing_date,
                          proxy_url=f.url(), n_pvp_years=len(years))
            matched = sct_parser.match_ceo_rows(rows, dict(zip(years["fy"], years["ceo_sct_total"])))
            sct = pd.DataFrame([{"fy": fy, "sct_year_label": r.year, "sct_name": r.name,
                                 **{c: r.values.get(c, 0.0) for c in sct_parser.COMPONENTS},
                                 "sct_total": r.total} for fy, r in matched.items()])
            status["n_sct_matched"] = len(sct)
        else:
            # Fallback: SCT only, from the newest proxy that parses.
            sct, f = pd.DataFrame(), None
            for f in proxies[:MAX_PROXIES_TO_TRY]:
                rows = sct_parser.first_person_rows(sct_parser.parse_sct(edgar.primary_html(f) or ""))
                if rows:
                    sct = pd.DataFrame([{"fy": r.year, "sct_year_label": r.year, "sct_name": r.name,
                                         **{c: r.values.get(c, 0.0) for c in sct_parser.COMPONENTS},
                                         "sct_total": r.total} for r in rows])
                    break
            years = pd.DataFrame()
            if not sct.empty:
                years = pd.DataFrame({"fy": sct["fy"], "ceo_sct_total": sct["sct_total"],
                                      "ceo_name": sct["sct_name"], "n_peos": 1,
                                      "multi_peo_year": False})
                status.update(pvp_source="sct_fallback", accession=f.accession,
                              filing_date=f.filing_date, proxy_url=f.url(),
                              n_pvp_years=0, n_sct_matched=len(sct))
            else:
                status["pvp_source"] = "none"
                if proxies:
                    status.update(accession=proxies[0].accession, filing_date=proxies[0].filing_date,
                                  proxy_url=proxies[0].url())
            peo = pd.DataFrame()
        for name, df in (("years", years), ("peo", peo), ("sct", sct)):
            if not df.empty:
                df = df.copy()
                df.insert(0, "ticker", ticker)
                df.insert(1, "cik", cik)
            out[name] = df
    except Exception as exc:  # keep going; record the failure
        status["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    return out


def run(sample: pd.DataFrame | None = None, workers: int = 4) -> dict[str, pd.DataFrame]:
    if sample is None:
        sample = pd.read_csv(config.DATA_PROCESSED / "sample.csv")
    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_company, r): r["ticker"] for _, r in sample.iterrows()}
        for i, fut in enumerate(as_completed(futs), 1):
            results.append(fut.result())
            if i % 10 == 0 or i == len(futs):
                print(f"[compensation] {i}/{len(futs)} companies processed")
    tables = {
        "pvp_company_years": pd.concat([r["years"] for r in results if not r["years"].empty], ignore_index=True),
        "pvp_peo_rows": pd.concat([r["peo"] for r in results if not r["peo"].empty], ignore_index=True),
        "sct_ceo_rows": pd.concat([r["sct"] for r in results if not r["sct"].empty], ignore_index=True),
        "edgar_status": pd.DataFrame([r["status"] for r in results]),
    }
    for name, df in tables.items():
        sort_cols = [c for c in ("ticker", "fy") if c in df.columns]
        df.sort_values(sort_cols).to_csv(config.DATA_PROCESSED / f"{name}.csv", index=False)
    st = tables["edgar_status"]
    print("[compensation] source counts:\n" + st["pvp_source"].value_counts(dropna=False).to_string())
    print(f"[compensation] SCT pay-mix matched for {int((st['n_sct_matched'] > 0).sum())} companies")
    return tables


if __name__ == "__main__":
    run()
