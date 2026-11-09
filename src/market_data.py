"""Phase 3 - Market data: independent TSR, proxy cross-check, fundamentals.

TSR methodology (independent of the proxy):
    total-return index  TRI_t = TRI_{t-1} * (Close_t + Div_t) / Close_{t-1}
using Yahoo's split-adjusted close and cash dividends reinvested on the
ex-date. Yahoo's own dividend-adjusted close is used only as a sanity check.

Outputs (data/processed):
* ``tsr_fiscal.csv``     - independent $100-index at every PvP fiscal year end,
                           side by side with the company-reported value
* ``tsr_windows.csv``    - 1/3/5-year TSR over each company's latest fiscal
                           windows (aligned with pay) + trailing calendar TSR
* ``fundamentals.csv``   - market cap, revenue growth, ROE, etc.
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

from . import config, http_cache

PRICE_CACHE = config.RAW_MARKET / "prices.csv.gz"
INFO_DIR = config.RAW_MARKET / "info"
FIN_DIR = config.RAW_MARKET / "financials"
PRICE_START = "2019-01-01"


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------
def load_prices(tickers: list[str]) -> pd.DataFrame:
    """Long table [date, ticker, close, adj_close, dividends, splits] (cached)."""
    cached = pd.read_csv(PRICE_CACHE, parse_dates=["date"]) if PRICE_CACHE.exists() else pd.DataFrame()
    have = set(cached["ticker"]) if not cached.empty else set()
    need = [t for t in tickers if t not in have]
    if need:
        print(f"[market] downloading prices for {len(need)} tickers")
        frames = []
        for i in range(0, len(need), 25):
            batch = need[i:i + 25]
            raw = yf.download(batch, start=PRICE_START, end=None, auto_adjust=False, actions=True,
                              group_by="ticker", progress=False, threads=True)
            for t in batch:
                try:
                    d = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
                except KeyError:
                    continue
                d = d.dropna(subset=["Close"])
                if d.empty:
                    continue
                frames.append(pd.DataFrame({
                    "date": d.index.tz_localize(None) if d.index.tz is not None else d.index,
                    "ticker": t, "close": d["Close"].values, "adj_close": d["Adj Close"].values,
                    "dividends": d.get("Dividends", pd.Series(0, index=d.index)).fillna(0).values,
                    "splits": d.get("Stock Splits", pd.Series(0, index=d.index)).fillna(0).values,
                }))
            time.sleep(1)
        new = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        cached = pd.concat([cached, new], ignore_index=True) if not cached.empty else new
        cached.to_csv(PRICE_CACHE, index=False)
    return cached[cached["ticker"].isin(tickers)].sort_values(["ticker", "date"]).reset_index(drop=True)


def total_return_index(px: pd.DataFrame) -> pd.Series:
    """Dividend-reinvested total-return index for one ticker (date index)."""
    px = px.sort_values("date")
    close = px["close"].to_numpy()
    div = px["dividends"].to_numpy()
    gross = np.ones(len(px))
    gross[1:] = (close[1:] + div[1:]) / close[:-1]
    return pd.Series(np.cumprod(gross), index=pd.DatetimeIndex(px["date"]))


def _at(series: pd.Series, d) -> float:
    """Last value on or before date ``d`` (NaN if none within 10 days)."""
    d = pd.Timestamp(d)
    s = series.loc[:d]
    if s.empty or (d - s.index[-1]).days > 10:
        return float("nan")
    return float(s.iloc[-1])


def tsr_between(tri: pd.Series, start, end) -> float:
    a, b = _at(tri, start), _at(tri, end)
    return b / a - 1 if a and a == a and b == b else float("nan")


# ---------------------------------------------------------------------------
# TSR against PvP fiscal periods
# ---------------------------------------------------------------------------
def fiscal_tsr(pvp: pd.DataFrame, tris: dict[str, pd.Series], tickers: dict[str, str]) -> pd.DataFrame:
    """Independent $100-index at each PvP fiscal year end (same base as proxy)."""
    rows = []
    for tk, g in pvp.groupby("ticker"):
        tri = tris.get(tickers.get(tk, tk))
        g = g.sort_values("fy")
        if tri is None or g.empty:
            continue
        base_date = date.fromisoformat(g["start"].iloc[0]) - timedelta(days=1)
        for r in g.itertuples():
            indep = 100 * (1 + tsr_between(tri, base_date, r.end))
            rows.append({"ticker": tk, "fy": r.fy, "end": r.end, "base_date": base_date.isoformat(),
                         "proxy_tsr_value": r.tsr_value, "indep_tsr_value": indep})
    df = pd.DataFrame(rows)
    df["diff_pts"] = df["indep_tsr_value"] - df["proxy_tsr_value"]
    df["discrepancy_flag"] = df["diff_pts"].abs() > config.TSR_DISCREPANCY_PP
    return _classify_discrepancies(df, tris, tickers)


def _classify_discrepancies(df: pd.DataFrame, tris: dict[str, pd.Series],
                            tickers: dict[str, str]) -> pd.DataFrame:
    """Diagnose *why* proxy and independent TSR disagree.

    * ``stale_base`` - the filer rolled its table forward but left earlier
      years measured from the previous (one-year-older) base date.
    * ``misdated``   - values are tagged one fiscal year early (the value at
      year t equals our value at year t+1).
    * ``other``      - methodology or data differences we cannot attribute.
    """
    df = df.copy()
    df["alt_base_value"] = np.nan
    df["discrepancy_reason"] = None
    tol = config.TSR_DISCREPANCY_PP / 2
    for tk, g in df.groupby("ticker"):
        tri = tris.get(tickers.get(tk, tk))
        if tri is None:
            continue
        old_base = date.fromisoformat(g["base_date"].iloc[0]) - timedelta(days=365)
        alt = g["end"].map(lambda e: 100 * (1 + tsr_between(tri, old_base, e)))
        df.loc[g.index, "alt_base_value"] = alt.values
        nxt = g["indep_tsr_value"].shift(-1)
        for i in g.index[g["discrepancy_flag"]]:
            p = df.at[i, "proxy_tsr_value"]
            if abs(df.at[i, "alt_base_value"] - p) <= tol:
                df.at[i, "discrepancy_reason"] = "stale_base"
            elif nxt.get(i) == nxt.get(i) and abs(nxt.get(i) - p) <= tol:
                df.at[i, "discrepancy_reason"] = "misdated"
            else:
                df.at[i, "discrepancy_reason"] = "other"
    return df


def window_tsr(pvp: pd.DataFrame, tris: dict[str, pd.Series], tickers: dict[str, str],
               as_of: str = config.AS_OF_DATE) -> pd.DataFrame:
    """1/3/5-year TSR ending at each company's latest fiscal year end, plus
    trailing calendar TSR to ``as_of``."""
    rows = []
    for tk, g in pvp.groupby("ticker"):
        g = g.sort_values("fy")
        tri = tris.get(tickers.get(tk, tk))
        rec = {"ticker": tk, "latest_fy": int(g["fy"].iloc[-1]), "latest_fy_end": g["end"].iloc[-1]}
        end = g["end"].iloc[-1]
        for n in config.WINDOWS:
            if len(g) >= n and tri is not None:
                start = date.fromisoformat(g["start"].iloc[-n]) - timedelta(days=1)
                r = tsr_between(tri, start, end)
                rec[f"tsr_{n}y"] = r
                rec[f"tsr_{n}y_ann"] = (1 + r) ** (1 / n) - 1 if r == r else np.nan
                rec[f"window_{n}y_start"] = start.isoformat()
                # proxy-reported equivalent over the same window (from $100 index)
                v_end = g["tsr_value"].iloc[-1]
                v_start = 100.0 if len(g) == n else g["tsr_value"].iloc[-n - 1]
                rec[f"proxy_tsr_{n}y"] = v_end / v_start - 1 if v_start and v_end == v_end and v_start == v_start else np.nan
                pv_end = g["peer_tsr_value"].iloc[-1]
                pv_start = 100.0 if len(g) == n else g["peer_tsr_value"].iloc[-n - 1]
                rec[f"peer_tsr_{n}y"] = pv_end / pv_start - 1 if pv_start and pv_end == pv_end and pv_start == pv_start else np.nan
            else:
                rec[f"tsr_{n}y"] = rec[f"tsr_{n}y_ann"] = rec[f"proxy_tsr_{n}y"] = rec[f"peer_tsr_{n}y"] = np.nan
        if tri is not None:
            for n in config.WINDOWS:
                s = pd.Timestamp(as_of) - pd.DateOffset(years=n)
                r = tsr_between(tri, s, as_of)
                rec[f"trailing_tsr_{n}y"] = r
        rows.append(rec)
    return pd.DataFrame(rows)


def adj_close_check(prices: pd.DataFrame, tris: dict[str, pd.Series]) -> pd.DataFrame:
    """Compare our 5-year TRI return with Yahoo's adjusted-close return."""
    out = []
    for tk, px in prices.groupby("ticker"):
        px = px.set_index("date")
        start, end = px.index[-1] - pd.DateOffset(years=5), px.index[-1]
        ours = tsr_between(tris[tk], start, end)
        yahoo = tsr_between(px["adj_close"], start, end)
        out.append({"yf_ticker": tk, "tri_5y": ours, "adjclose_5y": yahoo, "diff": ours - yahoo})
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------
INFO_FIELDS = ["marketCap", "sharesOutstanding", "totalRevenue", "revenueGrowth", "returnOnEquity",
               "returnOnAssets", "profitMargins", "trailingPE", "beta", "fullTimeEmployees",
               "currentPrice", "currency", "longName"]


def _info(tk: str, fetch: bool = True) -> dict:
    """Yahoo quote fields (cached). Empty or blocked responses are NOT cached,
    so a later run can retry; with fetch=False only the cache is read."""
    INFO_DIR.mkdir(parents=True, exist_ok=True)
    path = INFO_DIR / f"{tk}.json"
    if path.exists():
        return json.loads(path.read_text())
    if not fetch:
        return {}
    for attempt in range(2):
        try:
            info = yf.Ticker(tk).info or {}
            data = {k: info.get(k) for k in INFO_FIELDS}
            if data.get("marketCap"):
                path.write_text(json.dumps(data))
                return data
            return {}  # blocked / empty: do not cache, do not hammer the endpoint
        except Exception as exc:  # rate limits / transient errors
            print(f"[market] info {tk} attempt {attempt + 1} failed: {exc}")
            time.sleep(3 * (attempt + 1))
    return {}


def _revenue_history(tk: str, fetch: bool = True) -> pd.Series:
    FIN_DIR.mkdir(parents=True, exist_ok=True)
    path = FIN_DIR / f"{tk}_revenue.csv"
    if path.exists():
        s = pd.read_csv(path, index_col=0).iloc[:, 0]
        s.index = pd.to_datetime(s.index)
        return s
    if not fetch:
        return pd.Series(dtype=float)
    try:
        inc = yf.Ticker(tk).income_stmt
        row = next((r for r in ("Total Revenue", "Operating Revenue", "Revenue") if r in inc.index), None)
        s = inc.loc[row].dropna().sort_index() if row else pd.Series(dtype=float)
        if len(s):
            s.to_frame("revenue").to_csv(path)
        return s
    except Exception as exc:
        print(f"[market] income_stmt {tk} failed: {exc}")
    return pd.Series(dtype=float)


# --- SEC companyfacts: reported shares outstanding and annual revenue -------
COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
REVENUE_CONCEPTS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                    "RevenuesNetOfInterestExpense")


def _companyfacts(cik: int) -> dict:
    raw = http_cache.get(COMPANYFACTS.format(cik=int(cik)))
    return json.loads(raw) if raw else {}


def _sec_shares(facts: dict) -> pd.Series:
    """Shares outstanding by as-of date: the cover-page dei figure, else the
    weighted-average diluted count from the financial statements."""
    f = facts.get("facts", {})
    rows = f.get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
    if not rows:
        rows = f.get("us-gaap", {}).get("WeightedAverageNumberOfDilutedSharesOutstanding", {}).get("units", {}).get("shares", [])
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows).sort_values("filed").drop_duplicates("end", keep="last")
    return pd.Series(df["val"].astype(float).values, index=pd.to_datetime(df["end"])).sort_index()


def _sec_revenue(facts: dict) -> pd.Series:
    """Annual (10-K, ~12-month) revenue; the concept with the latest data wins."""
    g = facts.get("facts", {}).get("us-gaap", {})
    best = pd.Series(dtype=float)
    for c in REVENUE_CONCEPTS:
        rows = g.get(c, {}).get("units", {}).get("USD", [])
        df = pd.DataFrame(rows)
        if df.empty or "start" not in df:
            continue
        df = df[df["form"].astype(str).str.startswith("10-K")]
        dur = (pd.to_datetime(df["end"]) - pd.to_datetime(df["start"])).dt.days
        df = df[(dur > 330) & (dur < 400)].sort_values("filed").drop_duplicates("end", keep="last")
        if df.empty:
            continue
        s = pd.Series(df["val"].astype(float).values, index=pd.to_datetime(df["end"])).sort_index()
        if best.empty or s.index[-1] > best.index[-1] or (s.index[-1] == best.index[-1] and len(s) > len(best)):
            best = s
    return best


def _split_factor_after(px: pd.DataFrame, d) -> float:
    s = px.loc[px.index > pd.Timestamp(d), "splits"]
    s = s[s > 0]
    return float(np.prod(s.to_numpy())) if len(s) else 1.0


def fundamentals(sample: pd.DataFrame, prices: pd.DataFrame, windows: pd.DataFrame) -> pd.DataFrame:
    """Market cap, revenue and context ratios.

    Current market cap comes from Yahoo for the 100-company sample (unchanged
    method) and from SEC-reported shares x last close for the full universe
    (Yahoo's quote endpoint started refusing bulk requests); each falls back to
    the other. Size at the start of each pay window = current market cap x
    (price at window start / current price), so 'winners got bigger' does not
    contaminate the size control.
    """
    prefer_sec = config.FULL_UNIVERSE
    rows = []
    for r in sample.itertuples():
        info = _info(r.yf_ticker, fetch=not prefer_sec)
        facts = _companyfacts(r.cik)
        pxd = prices[prices["ticker"] == r.yf_ticker].set_index("date").sort_index()
        last = float(pxd["close"].iloc[-1]) if len(pxd) else np.nan
        sh = _sec_shares(facts)
        mcap_sec = np.nan
        if len(sh) and len(pxd):
            mcap_sec = sh.iloc[-1] * _split_factor_after(pxd, sh.index[-1]) * last
            if not 2e9 <= mcap_sec <= 2e13:  # implausible for an S&P 500 member (e.g. share-class units)
                mcap_sec = np.nan
        mcap_y = info.get("marketCap") or np.nan
        if prefer_sec:
            mcap_now, src = (mcap_sec, "sec") if mcap_sec == mcap_sec else (mcap_y, "yahoo")
        else:
            mcap_now, src = (mcap_y, "yahoo") if mcap_y == mcap_y else (mcap_sec, "sec")
        rec = {"ticker": r.ticker, **{f"yf_{k}": v for k, v in info.items()},
               "mcap_now": mcap_now, "mcap_now_source": src if mcap_now == mcap_now else None,
               "mcap_now_yahoo": mcap_y, "mcap_now_sec": mcap_sec}
        rev = _revenue_history(r.yf_ticker, fetch=not prefer_sec)
        rev_src = "yahoo"
        if prefer_sec or len(rev) < 2:
            rs = _sec_revenue(facts)
            if len(rs) >= 2 or (len(rs) and len(rev) < 2):
                rev, rev_src = rs.tail(5), "sec"
        if len(rev) >= 2:
            n = (rev.index[-1] - rev.index[0]).days / 365.25
            rec["revenue_cagr"] = (rev.iloc[-1] / rev.iloc[0]) ** (1 / n) - 1 if rev.iloc[0] > 0 and n > 0.5 else np.nan
            rec["revenue_cagr_years"] = round(n, 1)
        if len(rev):
            rec["revenue_latest"] = rev.iloc[-1]
            rec["revenue_source"] = rev_src
        w = windows[windows["ticker"] == r.ticker]
        for n in config.WINDOWS:
            col = f"window_{n}y_start"
            if not w.empty and col in w and isinstance(w[col].iloc[0], str) and mcap_now == mcap_now and len(pxd):
                p0 = _at(pxd["close"], w[col].iloc[0])
                rec[f"mcap_start_{n}y"] = mcap_now * p0 / last
        rows.append(rec)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
def run() -> dict[str, pd.DataFrame]:
    sample = pd.read_csv(config.DATA_PROCESSED / "sample.csv")
    pvp = pd.read_csv(config.DATA_PROCESSED / "pvp_company_years.csv")
    tick_map = dict(zip(sample["ticker"], sample["yf_ticker"]))
    prices = load_prices(sample["yf_ticker"].tolist())
    missing = sorted(set(sample["yf_ticker"]) - set(prices["ticker"]))
    if missing:
        print(f"[market] WARNING no prices for: {missing}")
    tris = {tk: total_return_index(px) for tk, px in prices.groupby("ticker")}

    fis = fiscal_tsr(pvp, tris, tick_map)
    win = window_tsr(pvp, tris, tick_map)
    chk = adj_close_check(prices, tris)
    fun = fundamentals(sample, prices, win)

    fis.to_csv(config.DATA_PROCESSED / "tsr_fiscal.csv", index=False)
    win.to_csv(config.DATA_PROCESSED / "tsr_windows.csv", index=False)
    chk.to_csv(config.DATA_PROCESSED / "tsr_adjclose_check.csv", index=False)
    fun.to_csv(config.DATA_PROCESSED / "fundamentals.csv", index=False)

    # Company-level cross-check summary
    xc = fis.groupby("ticker").agg(max_abs_diff_pts=("diff_pts", lambda s: s.abs().max()),
                                   n_years=("fy", "size"),
                                   n_flagged=("discrepancy_flag", "sum"),
                                   latest_year_diff_pts=("diff_pts", "last"),
                                   reasons=("discrepancy_reason",
                                            lambda s: ";".join(sorted(set(s.dropna()))))).reset_index()
    xc["tsr_discrepancy"] = xc["n_flagged"] > 0
    xc.to_csv(config.DATA_PROCESSED / "tsr_crosscheck.csv", index=False)
    print(f"[market] TRI vs Yahoo adj-close 5y: median |diff| = {chk['diff'].abs().median():.4f}")
    print(f"[market] proxy-vs-independent TSR: {int(xc['tsr_discrepancy'].sum())} companies with "
          f">{config.TSR_DISCREPANCY_PP:.0f}pt gap in at least one year; median |gap| = "
          f"{fis['diff_pts'].abs().median():.2f} pts")
    return {"fiscal": fis, "windows": win, "fundamentals": fun, "crosscheck": xc}


if __name__ == "__main__":
    run()
