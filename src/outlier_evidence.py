"""Phase 5a - Primary-source evidence for the outlier case studies.

1. **Say-on-pay results** for every sample company, parsed from the 8-K
   (Item 5.07) filed after each annual meeting. Support is computed as
   For / (For + Against + Abstain), the "votes cast" basis proxy advisers use.
2. **Proxy keyword snippets** for the outlier companies: sentences in the
   DEF 14A that mention one-time/special/retention/sign-on/inducement awards,
   founder status, multi-year grants, CEO transitions or say-on-pay outcomes.

Outputs:
* ``data/processed/say_on_pay.csv``
* ``data/processed/outlier_evidence.json``
"""
from __future__ import annotations

import json
import re

import lxml.html
import pandas as pd

from . import config, edgar, http_cache

SOP_START = "2024-01-01"


# ---------------------------------------------------------------------------
# Say-on-pay
# ---------------------------------------------------------------------------
def _doc_text(html: str) -> str:
    try:
        doc = lxml.html.fromstring(html.encode("utf-8", errors="replace"))
    except Exception:
        return ""
    for bad in doc.xpath("//script|//style"):
        bad.drop_tree()
    # keep table cells separated so numbers don't glue together
    for td in doc.iter("td", "th"):
        td.tail = " | " + (td.tail or "")
    for br in doc.iter("br", "p", "div", "tr"):
        br.tail = "\n" + (br.tail or "")
    text = doc.text_content().replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", text)


NUM = r"(\d{1,3}(?:,\d{3})+|\d{4,})"
# The compensation phrase that identifies the say-on-pay proposal ...
COMP_PAT = re.compile(
    r"compensation of (?:the |our )?(?:company[’']?s? |corporation[’']?s? )?(?:named executive|executive officers|neos?)"
    r"|named executive officers?[’']? compensation|executive compensation|compensation (?:paid|awarded) to"
    r"|neo compensation|say[- ]on[- ]pay", re.I)
# ... must sit near an advisory cue (either side).
ADVISORY = re.compile(r"advisory|non-binding|say[- ]on[- ]pay|approve", re.I)
DELIM = re.compile(
    r"\(\s*(?:\d{1,2}|[ivx]{1,5})\s*\)"                         # (3)  (iii)
    r"|\b(?:Proposal|Item|Matter)\s*(?:No\.?\s*)?(\d{1,2})\b"      # Proposal 4
    r"|(?:^|\n|\|)\s*\d{1,2}\s*[.)]\s*[A-Z]",                      # 4. Approval ...
    re.I | re.M)
PROP_NO = re.compile(r"(?:Proposal|Item|Matter)\s*(?:No\.?\s*)?(\d{1,2})\b[^\n]{0,120}$", re.I)


def parse_say_on_pay(text: str) -> dict | None:
    """Return For/Against/Abstain for the say-on-pay proposal, or None.

    The snippet runs from the say-on-pay description to the next proposal
    delimiter, so intro paragraphs that merely *list* proposals (followed by
    the director-election table) yield no numbers and are skipped. A
    delimiter that repeats the current proposal's own number ("...with
    respect to Proposal 3 are set forth below") does not end the snippet.
    """
    for m in COMP_PAT.finditer(text):
        ctx = text[max(0, m.start() - 250):m.end() + 250]
        if not ADVISORY.search(ctx):
            continue
        window_before = text[max(0, m.start() - 300):m.start()]
        if re.search(r"frequency", window_before[-150:] + text[m.start():m.start() + 250], re.I):
            continue
        own = PROP_NO.search(window_before)
        own_no = own.group(1) if own else None
        pos, stop = m.end(), min(len(text), m.start() + 1500)
        while True:
            nxt = DELIM.search(text, pos, stop)
            if not nxt:
                break
            if own_no and nxt.group(1) == own_no:
                pos = nxt.end()
                continue
            stop = nxt.start()
            break
        snippet = text[m.start():stop]
        if not re.search(r"\bfor\b|against", snippet, re.I):
            continue
        nums = [int(n.replace(",", "")) for n in re.findall(NUM, snippet)]
        nums = [n for n in nums if n >= 1000 and not (1990 <= n <= 2035)]
        if len(nums) < 3:
            continue
        f, a, ab = nums[0], nums[1], nums[2]
        if f <= 0 or a > f * 50:
            continue
        support = f / (f + a + ab)
        if not 0.05 < support <= 1.0:
            continue
        return {"for": f, "against": a, "abstain": ab, "support": support}
    return None


def say_on_pay(cik: int) -> list[dict]:
    df = edgar.filings_of(cik, {"8-K", "8-K/A"})
    df = df[(df["filingDate"] >= SOP_START) & df["items"].fillna("").str.contains("5.07")]
    out = []
    for r in df.itertuples():
        f = edgar.Filing(cik=cik, form=r.form, accession=r.accessionNumber, filing_date=r.filingDate,
                         report_date=r.reportDate or "", primary_doc=r.primaryDocument,
                         is_xbrl=bool(r.isXBRL), is_ixbrl=bool(r.isInlineXBRL))
        html = edgar.primary_html(f)
        if not html:
            continue
        res = parse_say_on_pay(_doc_text(html))
        if res:
            out.append({"cik": cik, "filing_date": r.filingDate, "meeting_date": r.reportDate,
                        "accession": r.accessionNumber, "url": f.url(), **res})
    return out


def say_on_pay_all(sample: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in sample.itertuples():
        try:
            for rec in say_on_pay(int(r.cik)):
                rows.append({"ticker": r.ticker, **rec})
        except Exception as exc:
            print(f"[evidence] say-on-pay {r.ticker} failed: {exc}")
    df = pd.DataFrame(rows)
    if not df.empty:
        # one vote per annual meeting (keep the first 8-K for a meeting date)
        df = df.sort_values(["ticker", "filing_date"]).drop_duplicates(["ticker", "meeting_date"])
    df.to_csv(config.DATA_PROCESSED / "say_on_pay.csv", index=False)
    return df


# ---------------------------------------------------------------------------
# Proxy keyword evidence
# ---------------------------------------------------------------------------
KEYWORDS = {
    "one_time_award": r"one[- ]time|special (?:equity |performance |retention )?(?:award|grant)|mega[- ]grant|"
                      r"front[- ]loaded|multi[- ]year (?:equity )?(?:award|grant)",
    "retention": r"retention (?:award|grant|rsu|equity)",
    "new_ceo": r"sign[- ]on|inducement|make[- ]whole|new hire|appointed (?:as )?(?:our )?chief executive",
    "founder": r"\bfounder\b|co-founder",
    "say_on_pay": r"say[- ]on[- ]pay|approximately \d{1,3}(?:\.\d)?% of (?:the )?votes cast",
    "no_grant": r"did not (?:receive|grant)|no (?:new )?(?:equity|stock) awards?|biennial|every (?:other|two) years?",
    "performance_award": r"performance[- ](?:based )?(?:stock )?options?|performance[- ]vested|stock price hurdle",
    "carry_incentive": r"carried interest|incentive fee|performance (?:income|fee)|profits interest",
}


def proxy_snippets(html: str, max_per_kw: int = 6) -> dict[str, list[str]]:
    text = _doc_text(html)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n{2,}", text)
    out: dict[str, list[str]] = {}
    for key, pat in KEYWORDS.items():
        rx = re.compile(pat, re.I)
        hits = []
        for s in sentences:
            s2 = re.sub(r"\s+", " ", s).strip(" |")
            if 40 < len(s2) < 700 and rx.search(s2) and s2 not in hits:
                hits.append(s2)
            if len(hits) >= max_per_kw:
                break
        out[key] = hits
    return out


def run_say_on_pay() -> pd.DataFrame:
    sample = pd.read_csv(config.DATA_PROCESSED / "sample.csv")
    sop = say_on_pay_all(sample)
    print(f"[evidence] say-on-pay parsed for {sop['ticker'].nunique() if not sop.empty else 0}/"
          f"{len(sample)} companies ({len(sop)} meetings)")
    return sop


def run(tickers: list[str] | None = None) -> dict:
    """Proxy snippets for the outliers (needs results.json and say_on_pay.csv)."""
    P = config.DATA_PROCESSED
    sop = pd.read_csv(P / "say_on_pay.csv")
    if tickers is None:
        res = json.loads((config.ROOT / "output" / "results.json").read_text())["outliers"]
        tickers = [o["ticker"] for o in res["overpaid"] + res["underpaid"]] + \
                  [o["ticker"] for o in res["misaligned_high_pay_low_tsr"][:1]]
    st = pd.read_csv(P / "edgar_status.csv").set_index("ticker")
    evidence = {}
    for tk in dict.fromkeys(tickers):
        html = http_cache.get(st.loc[tk, "proxy_url"]) or ""
        evidence[tk] = {"proxy_url": st.loc[tk, "proxy_url"], "snippets": proxy_snippets(html),
                        "say_on_pay": sop[sop["ticker"] == tk].to_dict(orient="records") if not sop.empty else []}
    (P / "outlier_evidence.json").write_text(json.dumps(evidence, indent=2, default=str))
    return evidence


if __name__ == "__main__":
    run_say_on_pay()
    run()
