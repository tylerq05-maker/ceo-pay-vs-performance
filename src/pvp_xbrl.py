"""Phase 2a - Pay-Versus-Performance (Item 402(v)) data from DEF 14A XBRL.

The SEC's Executive Compensation Disclosure taxonomy (``ecd``) tags the PvP
table. We read the extracted XBRL instance that EDGAR generates for every
inline-XBRL filing and pull, per fiscal year:

* ``PeoTotalCompAmt``             - CEO pay as reported in the Summary Comp Table
* ``PeoActuallyPaidCompAmt``      - "compensation actually paid" (CAP)
* ``TotalShareholderRtnAmt``      - value of $100 invested at the start of the table
* ``PeerGroupTotalShareholderRtnAmt``
* ``NonPeoNeoAvgTotalCompAmt`` / ``NonPeoNeoAvgCompActuallyPaidAmt``
* ``us-gaap:NetIncomeLoss``, ``CoSelectedMeasureAmt`` / ``CoSelectedMeasureName``

When a company had more than one PEO in a year, facts are reported per person
on ``ecd:IndividualAxis``. Those are kept individually (``peo_rows``) and the
company-year record identifies the *year-end incumbent* (see ``_pick_incumbent``).
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

import pandas as pd
from lxml import etree

XBRLI = "{http://www.xbrl.org/2003/instance}"
XBRLDI = "{http://xbrl.org/2006/xbrldi}"

PEO_CONCEPTS = {"PeoTotalCompAmt": "sct_total", "PeoActuallyPaidCompAmt": "cap"}
TSR_CONCEPTS = {
    "TotalShareholderRtnAmt": "tsr_value",
    "PeerGroupTotalShareholderRtnAmt": "peer_tsr_value",
}
CO_CONCEPTS = {
    **TSR_CONCEPTS,
    "NonPeoNeoAvgTotalCompAmt": "nonpeo_avg_sct",
    "NonPeoNeoAvgCompActuallyPaidAmt": "nonpeo_avg_cap",
    "CoSelectedMeasureAmt": "csm_value",
}
ALLOWED_PEO_AXES = {"IndividualAxis", "ExecutiveCategoryAxis"}


def fiscal_year_label(end: date) -> int:
    """Compustat convention: FY = calendar year of the period end if it ends
    in June or later, otherwise the prior year (e.g. FYE Jan-2026 -> FY2025)."""
    return end.year if end.month >= 6 else end.year - 1


def _local(qname: str | None) -> str:
    return (qname or "").split(":")[-1]


def _member_to_name(member: str) -> str:
    """'sbux:KevinJohnsonMember' -> 'Kevin Johnson' (fallback when no PeoName)."""
    m = _local(member)
    m = re.sub(r"Member$", "", m)
    m = re.sub(r"([a-z])([A-Z])", r"\1 \2", m)
    return m.strip()


def name_key(name: str | None) -> str:
    """Letters-only lowercase key used to match the same person across years
    ('Robert KOrtberg' == 'Robert K. Ortberg')."""
    return re.sub(r"[^a-z]", "", (name or "").lower())


def same_person(a: str | None, b: str | None) -> bool:
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    short, long_ = sorted((ka, kb), key=len)
    if len(short) >= 6 and short in long_:  # 'davidgibbs' in 'davidgibbschiefexecutive...'
        return True
    la = re.sub(r"[^a-z ]", "", (a or "").lower()).split()
    lb = re.sub(r"[^a-z ]", "", (b or "").lower()).split()
    honor = {"mr", "ms", "mrs", "dr", "jr", "sr", "ii", "iii"}
    la = [t for t in la if t not in honor]
    lb = [t for t in lb if t not in honor]
    return bool(la and lb and la[-1] == lb[-1])


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text.strip())
    except ValueError:
        return None


def parse_instance(xml_bytes: bytes) -> dict:
    """Return contexts and raw ecd/us-gaap facts from an XBRL instance."""
    parser = etree.XMLParser(huge_tree=True, recover=True)
    root = etree.fromstring(xml_bytes, parser)
    contexts: dict[str, dict] = {}
    for c in root.iter(XBRLI + "context"):
        sd = c.findtext(f".//{XBRLI}startDate")
        ed = c.findtext(f".//{XBRLI}endDate")
        inst = c.findtext(f".//{XBRLI}instant")
        dims = {_local(m.get("dimension")): (m.text or "").strip()
                for m in c.iter(XBRLDI + "explicitMember")}
        for t in c.iter(XBRLDI + "typedMember"):
            dims[_local(t.get("dimension"))] = "typed"
        contexts[c.get("id")] = {"start": sd, "end": ed, "instant": inst, "dims": dims}

    facts = []
    seen = set()
    for el in root:
        if not isinstance(el.tag, str):
            continue
        q = etree.QName(el)
        ns = q.namespace or ""
        is_ecd = "xbrl.sec.gov/ecd" in ns
        is_ni = "fasb.org/us-gaap" in ns and q.localname == "NetIncomeLoss"
        if not (is_ecd or is_ni):
            continue
        ctx = el.get("contextRef")
        text = el.text if len(el) == 0 else etree.tostring(el, method="text", encoding="unicode")
        key = (q.localname, ctx, (text or "")[:200])
        if key in seen:  # filings frequently repeat identical facts
            continue
        seen.add(key)
        facts.append({"concept": q.localname, "context": ctx, "text": text,
                      "decimals": el.get("decimals"), "order": len(facts)})
    return {"contexts": contexts, "facts": facts}


def _is_annual(ctx: dict) -> bool:
    if not (ctx.get("start") and ctx.get("end")):
        return False
    d = (date.fromisoformat(ctx["end"]) - date.fromisoformat(ctx["start"])).days
    return 330 <= d <= 400


def build_tables(parsed: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (company_years, peo_rows) DataFrames for one filing."""
    ctxs, facts = parsed["contexts"], parsed["facts"]

    co = defaultdict(dict)                       # period -> field -> value
    peo = defaultdict(lambda: defaultdict(dict))  # period -> member -> field -> value
    peo_names_dim = defaultdict(dict)            # period -> member -> name
    peo_names_nodim = defaultdict(list)          # period -> [names in doc order]
    csm_name = None
    tsr_by_end = defaultdict(dict)               # end date -> tsr fields

    for f in facts:
        ctx = ctxs.get(f["context"])
        if ctx is None:
            continue
        concept = f["concept"]
        if concept == "CoSelectedMeasureName" and not ctx["dims"]:
            csm_name = csm_name or (f["text"] or "").strip()[:120]
            continue
        if concept in TSR_CONCEPTS and not ctx["dims"]:
            # Filers use either one-year contexts or cumulative contexts
            # (base date -> year end) for TSR; key by the end date.
            end = ctx.get("end") or ctx.get("instant")
            v = _num(f["text"])
            if end and v is not None:
                tsr_by_end[end].setdefault(TSR_CONCEPTS[concept], v)
            continue
        if not _is_annual(ctx):
            continue
        period = (ctx["start"], ctx["end"])
        dims = ctx["dims"]
        if concept == "PeoName":
            name = re.sub(r"\s+", " ", (f["text"] or "")).strip()
            if not name or "NonPeo" in dims.get("ExecutiveCategoryAxis", ""):
                continue  # some filers (e.g. Apple) misuse PeoName for other NEOs
            if "IndividualAxis" in dims and set(dims) <= ALLOWED_PEO_AXES:
                peo_names_dim[period][dims["IndividualAxis"]] = name
            elif not dims or set(dims) == {"ExecutiveCategoryAxis"}:
                peo_names_nodim[period].append(name)
            continue
        if concept in PEO_CONCEPTS:
            if not set(dims) <= ALLOWED_PEO_AXES or "NonPeo" in dims.get("ExecutiveCategoryAxis", ""):
                continue
            member = dims.get("IndividualAxis", "__nodim__")
            v = _num(f["text"])
            if v is not None:
                peo[period][member][PEO_CONCEPTS[concept]] = v
            continue
        if concept in CO_CONCEPTS or concept == "NetIncomeLoss":
            if dims:
                continue
            v = _num(f["text"])
            if v is not None:
                co[period][CO_CONCEPTS.get(concept, "net_income")] = v

    periods = sorted(set(co) | set(peo), key=lambda p: p[1])
    peo_records = []
    for period in periods:
        members = peo.get(period, {})
        dim_members = {m: v for m, v in members.items() if m != "__nodim__"}
        serving = {m: v for m, v in dim_members.items()
                   if (v.get("sct_total") or 0) != 0 or (v.get("cap") or 0) != 0}
        # Some filers tag one CEO's numbers under two generic members
        # ("First PEO"/"Second PEO"); identical values = one person.
        uniq, seen_vals = {}, set()
        for m, v in serving.items():
            key = (v.get("sct_total"), v.get("cap"))
            if key not in seen_vals:
                seen_vals.add(key)
                uniq[m] = v
        serving = uniq
        if serving:
            for m, v in serving.items():
                name = peo_names_dim[period].get(m) or _member_to_name(m)
                peo_records.append({"start": period[0], "end": period[1], "member": _local(m),
                                    "peo_name": name, **v, "source": "dimensional"})
        elif "__nodim__" in members:
            names = peo_names_nodim.get(period, []) or list(peo_names_dim.get(period, {}).values())
            peo_records.append({"start": period[0], "end": period[1], "member": "",
                                "peo_name": names[0] if names else None,
                                **members["__nodim__"], "source": "non-dimensional",
                                "peo_name_ambiguous": len(set(names)) > 1})
    peo_df = pd.DataFrame(peo_records)
    if not peo_df.empty:
        # some filers tag only one of the two PEO concepts (e.g. J.B. Hunt)
        for col in ("sct_total", "cap"):
            if col not in peo_df.columns:
                peo_df[col] = float("nan")
    if not peo_df.empty and peo_df["peo_name"].isna().any():
        # Single-PEO filers often tag the name only once; borrow it for the
        # other non-dimensional years (only when no multi-PEO year exists).
        nd = peo_df[peo_df["source"] == "non-dimensional"]["peo_name"].dropna()
        if len(nd) and (peo_df["source"] == "non-dimensional").all():
            peo_df["peo_name"] = peo_df["peo_name"].fillna(nd.mode().iloc[0])

    co_records = []
    for period in periods:
        rec = {"start": period[0], "end": period[1], **co.get(period, {})}
        for k, v in tsr_by_end.get(period[1], {}).items():
            rec[k] = v
        nodim = peo.get(period, {}).get("__nodim__", {})
        rec["nodim_sct_total"] = nodim.get("sct_total")
        rec["nodim_cap"] = nodim.get("cap")
        co_records.append(rec)
    co_df = pd.DataFrame(co_records)
    for col in [*CO_CONCEPTS.values(), "net_income"]:
        if col not in co_df.columns:
            co_df[col] = float("nan")
    if not co_df.empty:
        co_df["csm_name"] = csm_name
        co_df["fy"] = co_df["end"].map(lambda e: fiscal_year_label(date.fromisoformat(e)))
        # Drop stray annual contexts that are not part of the PvP table
        has_data = co_df[["tsr_value"]].notna().any(axis=1) | co_df["end"].isin(
            peo_df["end"] if not peo_df.empty else [])
        co_df = co_df[has_data].reset_index(drop=True)
    if not peo_df.empty:
        peo_df["fy"] = peo_df["end"].map(lambda e: fiscal_year_label(date.fromisoformat(e)))
    return co_df, peo_df


def _pick_incumbent(peo_df: pd.DataFrame) -> dict[int, str]:
    """For each FY, choose the PEO in office at fiscal year-end.

    Rules, applied in order when a year lists several PEOs:
      1. the PEO who also appears in the following fiscal year;
      2. otherwise the PEO who did NOT appear in the prior year (the newcomer);
      3. otherwise the PEO with the highest Summary Comp Table total.
    """
    out: dict[int, str] = {}
    by_year = {fy: g for fy, g in peo_df.groupby("fy")}
    years = sorted(by_year)
    for i, fy in enumerate(years):
        g = by_year[fy]
        names = list(g["peo_name"].fillna(g["member"]))
        if len(names) == 1:
            out[fy] = names[0]
            continue
        nxt = set(by_year[years[i + 1]]["peo_name"].fillna(by_year[years[i + 1]]["member"])) if i + 1 < len(years) else set()
        prv = set(by_year[years[i - 1]]["peo_name"].fillna(by_year[years[i - 1]]["member"])) if i > 0 else set()
        cand = [n for n in names if any(same_person(n, x) for x in nxt)]
        if len(cand) != 1:
            cand2 = [n for n in names if not any(same_person(n, x) for x in prv)] if prv else []
            cand = cand2 if len(cand2) == 1 else cand
        if len(cand) != 1:
            g2 = g.assign(_n=names).sort_values("sct_total", ascending=False)
            cand = [g2["_n"].iloc[0]]
        out[fy] = cand[0]
    return out


def backfill_names(peo_df: pd.DataFrame, total_to_name: dict[float, str]) -> pd.DataFrame:
    """Fill missing PEO names from SCT rows whose Total equals the PEO total."""
    if peo_df.empty or not total_to_name:
        return peo_df
    peo_df = peo_df.copy()
    for i, r in peo_df[peo_df["peo_name"].isna()].iterrows():
        tot = r.get("sct_total")
        for t, nm in total_to_name.items():
            if tot and abs(t - tot) <= 0.005 * abs(tot) and nm:
                peo_df.at[i, "peo_name"] = nm
                break
    return peo_df


CO_PAY_COLS = ["nonpeo_avg_sct", "nonpeo_avg_cap", "nodim_sct_total", "nodim_cap"]
PEO_PAY_COLS = ["sct_total", "cap"]


def pay_scale(co_df: pd.DataFrame, peo_df: pd.DataFrame) -> int:
    """1000 when a filer tagged its pay figures in $ thousands, else 1.

    XBRL monetary facts must be in whole dollars, but some filers tag the
    printed (thousands) number. No S&P 500 company pays both its CEO and its
    other named officers under $100,000 on median, so when both medians are
    below that the figures are in thousands (Devon Energy: $14,883 = $14.9M).
    """
    peo_vals = peo_df["sct_total"] if not peo_df.empty and "sct_total" in peo_df else co_df.get("nodim_sct_total")
    non = co_df.get("nonpeo_avg_sct")
    if peo_vals is None or non is None:
        return 1
    mp, mn = pd.Series(peo_vals).abs().median(), pd.Series(non).abs().median()
    return 1000 if (0 < mp < 100_000 and 0 < mn < 100_000) else 1


def rescale_pay(co_df: pd.DataFrame, peo_df: pd.DataFrame, scale: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    co_df, peo_df = co_df.copy(), peo_df.copy()
    for c in CO_PAY_COLS:
        if c in co_df:
            co_df[c] = co_df[c] * scale
    for c in PEO_PAY_COLS:
        if c in peo_df:
            peo_df[c] = peo_df[c] * scale
    return co_df, peo_df


def company_year_table(co_df: pd.DataFrame, peo_df: pd.DataFrame) -> pd.DataFrame:
    """One row per fiscal year with incumbent-CEO pay, CEO-seat totals and flags."""
    if co_df.empty:
        return co_df
    df = co_df.copy()
    if peo_df.empty:
        df["ceo_sct_total"] = df["nodim_sct_total"]
        df["ceo_cap"] = df["nodim_cap"]
        df["ceo_name"] = None
        df["n_peos"] = df["ceo_sct_total"].notna().astype(int)
    else:
        inc = _pick_incumbent(peo_df)
        peo_df = peo_df.assign(_n=peo_df["peo_name"].fillna(peo_df["member"]))
        rows = []
        for fy, g in peo_df.groupby("fy"):
            sel = g[g["_n"] == inc[fy]].iloc[0]
            rows.append({"fy": fy, "ceo_name": inc[fy], "ceo_sct_total": sel.get("sct_total"),
                         "ceo_cap": sel.get("cap"), "n_peos": len(g),
                         "seat_sct_total": g["sct_total"].sum(min_count=1),
                         "seat_cap": g["cap"].sum(min_count=1),
                         "all_peos": "; ".join(g["_n"].astype(str))})
        df = df.merge(pd.DataFrame(rows), on="fy", how="left")
        # Single-CEO years where the filer tagged one figure on the CEO's
        # member and the other without a dimension (J.B. Hunt, Williams):
        # the undimensioned figure is that CEO's.
        one = df["n_peos"].fillna(0) == 1
        for c in ("ceo_sct_total", "ceo_cap", "seat_sct_total", "seat_cap", "nodim_sct_total", "nodim_cap"):
            if c in df:
                df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
        for col, nodim in (("ceo_sct_total", "nodim_sct_total"), ("ceo_cap", "nodim_cap")):
            if nodim in df:
                fill = one & df[col].isna() & df[nodim].notna()
                df.loc[fill, col] = df.loc[fill, nodim]
                if col == "ceo_sct_total":
                    df.loc[fill, "seat_sct_total"] = df.loc[fill, nodim]
        # A year with the CEO's CAP tagged but no SCT total anywhere, when the
        # filing does tag SCT totals in other years, is a "—" ($0) row that the
        # filer left untagged (Tesla 2021-23: Musk received no new pay).
        if df["ceo_sct_total"].notna().any():
            zero = one & df["ceo_sct_total"].isna() & df["ceo_cap"].notna()
            if "nodim_sct_total" in df:
                zero &= df["nodim_sct_total"].isna()
            df["sct_zero_inferred"] = zero
            df.loc[zero, ["ceo_sct_total", "seat_sct_total"]] = 0.0
    df["multi_peo_year"] = df["n_peos"].fillna(0) > 1
    df = df.sort_values("fy").reset_index(drop=True)
    # Annual company TSR implied by the cumulative $100 series.
    base = pd.concat([pd.Series([100.0]), df["tsr_value"].iloc[:-1]], ignore_index=True)
    df["tsr_annual"] = df["tsr_value"].values / base.values - 1
    pbase = pd.concat([pd.Series([100.0]), df["peer_tsr_value"].iloc[:-1]], ignore_index=True) \
        if "peer_tsr_value" in df else None
    if pbase is not None:
        df["peer_tsr_annual"] = df["peer_tsr_value"].values / pbase.values - 1
    return df
