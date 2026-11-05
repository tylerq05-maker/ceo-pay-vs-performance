"""SEC EDGAR filing discovery and download helpers (all calls cached)."""
from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

from . import config, http_cache

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SUBMISSIONS_PAGE = "https://data.sec.gov/submissions/{name}"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{name}"
INDEX_JSON = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/index.json"

PROXY_FORMS = {"DEF 14A"}


@dataclass
class Filing:
    cik: int
    form: str
    accession: str
    filing_date: str
    report_date: str
    primary_doc: str
    is_xbrl: bool
    is_ixbrl: bool

    @property
    def accn_nodash(self) -> str:
        return self.accession.replace("-", "")

    def url(self, name: str | None = None) -> str:
        return ARCHIVE.format(cik=self.cik, accn=self.accn_nodash, name=name or self.primary_doc)

    @property
    def index_url(self) -> str:
        return f"https://www.sec.gov/Archives/edgar/data/{self.cik}/{self.accn_nodash}/{self.accession}-index.html"


def _frame(block: dict) -> pd.DataFrame:
    cols = ["accessionNumber", "filingDate", "reportDate", "form", "primaryDocument",
            "isXBRL", "isInlineXBRL", "items"]
    return pd.DataFrame({c: block.get(c, [None] * len(block["form"])) for c in cols})


def submissions(cik: int) -> tuple[dict, pd.DataFrame]:
    """Company metadata + every filing (recent block plus paged history)."""
    meta = json.loads(http_cache.get(SUBMISSIONS.format(cik=cik)))
    frames = [_frame(meta["filings"]["recent"])]
    for page in meta["filings"].get("files", []):
        # Older pages are only needed when the recent block is crowded with
        # other forms (e.g. banks filing thousands of 424B2s). Load lazily:
        # only fetch pages that overlap the proxy-season years we need.
        if page.get("filingTo", "9999") < "2022-01-01":
            continue
        frames.append(_frame(json.loads(http_cache.get(SUBMISSIONS_PAGE.format(name=page["name"])))))
    df = pd.concat(frames, ignore_index=True)
    return meta, df


def proxy_filings(cik: int) -> list[Filing]:
    """All DEF 14A filings, newest first."""
    _, df = submissions(cik)
    df = df[df["form"].isin(PROXY_FORMS)].sort_values("filingDate", ascending=False)
    out = []
    for r in df.itertuples():
        out.append(Filing(cik=cik, form=r.form, accession=r.accessionNumber,
                          filing_date=r.filingDate, report_date=r.reportDate or "",
                          primary_doc=r.primaryDocument, is_xbrl=bool(r.isXBRL),
                          is_ixbrl=bool(r.isInlineXBRL)))
    return out


def filings_of(cik: int, forms: set[str]) -> pd.DataFrame:
    _, df = submissions(cik)
    return df[df["form"].isin(forms)].sort_values("filingDate", ascending=False)


def filing_index(f: Filing) -> list[dict]:
    raw = http_cache.get(INDEX_JSON.format(cik=f.cik, accn=f.accn_nodash))
    if raw is None:
        return []
    return json.loads(raw)["directory"]["item"]


def xbrl_instance_name(f: Filing) -> str | None:
    """Name of the extracted XBRL instance (``*_htm.xml``) for an iXBRL filing."""
    items = [i["name"] for i in filing_index(f)]
    cands = [n for n in items if n.endswith("_htm.xml")]
    if cands:
        primary_stem = f.primary_doc.rsplit(".", 1)[0]
        cands.sort(key=lambda n: (not n.startswith(primary_stem), len(n)))
        return cands[0]
    # Older (non-inline) XBRL submissions ship a plain instance file.
    plain = [n for n in items if n.endswith(".xml") and not any(
        n.endswith(s) for s in ("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml", "FilingSummary.xml"))
        and "MetaLinks" not in n]
    return plain[0] if plain else None


def primary_html(f: Filing) -> str | None:
    return http_cache.get(f.url())


def company_meta(cik: int) -> dict:
    meta, _ = submissions(cik)
    return {k: meta.get(k) for k in ("name", "sic", "sicDescription", "fiscalYearEnd",
                                      "stateOfIncorporation", "category")}
