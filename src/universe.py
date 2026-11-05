"""Phase 1 - S&P 500 universe and sector-stratified sample.

Sources
-------
* Constituents + GICS sector + CIK: Wikipedia "List of S&P 500 companies"
  (the most widely used free, regularly maintained constituent list).
* CIK cross-check: SEC ``company_tickers.json``.

Output: ``data/processed/universe.csv`` (all constituents, one row per company)
and ``data/processed/sample.csv`` (the companies actually analysed).
"""
from __future__ import annotations

import io
import json

import numpy as np
import pandas as pd

from . import config, http_cache

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def fetch_constituents() -> pd.DataFrame:
    html = http_cache.get(WIKI_URL, config.RAW_UNIVERSE)
    tables = pd.read_html(io.StringIO(html), attrs={"id": "constituents"})
    df = tables[0]
    df = df.rename(columns={
        "Symbol": "ticker", "Security": "company", "GICS Sector": "sector",
        "GICS Sub-Industry": "sub_industry", "CIK": "cik", "Date added": "date_added",
        "Founded": "founded", "Headquarters Location": "hq",
    })
    df["ticker"] = df["ticker"].astype(str).str.strip()
    df["cik"] = df["cik"].astype(int)
    # yfinance uses '-' for share classes (BRK.B -> BRK-B)
    df["yf_ticker"] = df["ticker"].str.replace(".", "-", regex=False)
    return df[["ticker", "yf_ticker", "company", "sector", "sub_industry", "cik", "hq",
               "date_added", "founded"]]


def crosscheck_cik(df: pd.DataFrame) -> pd.DataFrame:
    raw = http_cache.get(SEC_TICKERS_URL, config.RAW_UNIVERSE)
    sec = pd.DataFrame(json.loads(raw).values())
    sec["ticker"] = sec["ticker"].str.upper()
    sec_map = dict(zip(sec["ticker"], sec["cik_str"].astype(int)))
    df = df.copy()
    df["sec_cik"] = df["yf_ticker"].map(sec_map).fillna(df["ticker"].map(sec_map))
    df["cik_mismatch"] = df["sec_cik"].notna() & (df["sec_cik"] != df["cik"])
    # If Wikipedia and SEC disagree, trust SEC (it is the filer of record).
    df.loc[df["cik_mismatch"], "cik"] = df.loc[df["cik_mismatch"], "sec_cik"].astype(int)
    return df


def dedupe_share_classes(df: pd.DataFrame) -> pd.DataFrame:
    """Keep one row per CIK (e.g. GOOGL/GOOG, FOXA/FOX, NWSA/NWS).

    The Class A listing is kept; in the current index every such pair is
    distinguished by an extra trailing letter on the Class A ticker
    (GOOGL, FOXA, NWSA), so the longer ticker wins.
    """
    df = df.assign(_len=df["ticker"].str.len()).sort_values(["cik", "_len"], ascending=[True, False])
    dup = df.duplicated("cik", keep=False)
    alt = (df[dup].groupby("cik")["ticker"].apply(lambda s: "/".join(sorted(s))))
    out = df.drop_duplicates("cik", keep="first").drop(columns="_len").sort_values("ticker").copy()
    out["share_classes"] = out["cik"].map(alt)
    return out.reset_index(drop=True)


def stratified_sample(df: pd.DataFrame, n: int, seed: int = config.RANDOM_SEED) -> pd.DataFrame:
    """Proportional allocation by GICS sector (largest-remainder rounding),
    random draw within each sector. Every sector gets at least 2 names."""
    counts = df["sector"].value_counts()
    quota = counts / counts.sum() * n
    alloc = np.floor(quota).astype(int).clip(lower=2)
    remaining = n - alloc.sum()
    if remaining > 0:
        order = (quota - np.floor(quota)).sort_values(ascending=False).index
        for sector in order[:remaining]:
            alloc[sector] += 1
    elif remaining < 0:
        order = (quota - np.floor(quota)).sort_values().index
        for sector in order:
            if remaining == 0:
                break
            if alloc[sector] > 2:
                alloc[sector] -= 1
                remaining += 1
    rng = np.random.default_rng(seed)
    parts = []
    for sector, k in alloc.items():
        pool = df[df["sector"] == sector]
        idx = rng.choice(pool.index.to_numpy(), size=min(k, len(pool)), replace=False)
        parts.append(df.loc[idx])
    return pd.concat(parts).sort_values(["sector", "ticker"]).reset_index(drop=True)


def build(full: bool = config.FULL_UNIVERSE, n: int = config.SAMPLE_SIZE) -> pd.DataFrame:
    df = dedupe_share_classes(crosscheck_cik(fetch_constituents()))
    df.to_csv(config.DATA_PROCESSED / "universe.csv", index=False)
    sample = df.copy() if full else stratified_sample(df, n)
    sample.to_csv(config.DATA_PROCESSED / "sample.csv", index=False)
    print(f"[universe] {len(df)} unique companies; analysing {len(sample)} "
          f"({'full universe' if full else 'stratified sample'})")
    print(f"[universe] CIK mismatches vs SEC (SEC used): {int(df['cik_mismatch'].sum())}")
    print(sample["sector"].value_counts().to_string())
    return sample


if __name__ == "__main__":
    build()
