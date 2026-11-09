"""Phase 2b - Summary Compensation Table (SCT) parser for DEF 14A HTML.

Used for two things:
1. **Pay mix** (salary / bonus / stock / options / non-equity incentive /
   pension & NQDC / other) - this breakdown is *not* in the PvP XBRL.
2. **Fallback** CEO total pay for any company without PvP XBRL.

Proxy HTML is notoriously irregular (spacer cells, rowspans, '$' in separate
cells, footnote markers). Rather than relying on column positions, each row is
read as an ordered *sequence* of values and matched to the ordered header
labels. Every parsed row is then validated:

* components must sum to the row's Total (within 1% or $10k), and
* when PvP XBRL exists, the row's Total must equal the XBRL PEO total for that
  fiscal year (within 0.5%) - this positively identifies the CEO's row.

Rows that fail validation are discarded, so pay-mix data is only reported
where it reconciles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import lxml.html

COMPONENTS = ["salary", "bonus", "stock", "option", "neip", "pension", "other"]

YEAR_RE = re.compile(r"^(?:fy\s*|fiscal\s*)?(20[0-3]\d)(?:\s*\(\w\))?$", re.I)
FOOTNOTE_RE = re.compile(r"^(?:\(\s*[a-z0-9]{1,3}\s*\)|\*+|[a-z]\))+$", re.I)
DASH_RE = re.compile(r"^[-–—‒−—–-]+$")


def _clean(text: str) -> str:
    text = text.replace("\xa0", " ").replace("​", "")
    return re.sub(r"\s+", " ", text).strip()


def classify_header(label: str) -> str | None:
    # Space-insensitive: HTML line breaks often glue words ("StockAwards").
    t = re.sub(r"[^a-z]", "", label.lower())
    if "total" in t and any(w in t for w in ("without", "excluding", "excl", "lesschange")):
        return None  # supplemental "Total without change in pension value" column
    if t.startswith("total"):
        return "total"
    if "name" in t or "principalposition" in t:
        return "name"
    if re.fullmatch(r"(fiscal)?year[a-z]?", t) or t in {"fy"}:
        return "year"
    if "salary" in t:
        return "salary"
    if "allother" in t:
        return "other"
    if "nonequity" in t or "incentiveplan" in t:
        return "neip"
    if "pension" in t or "deferredcompensation" in t or "nonqualified" in t:
        return "pension"
    if "option" in t:
        return "option"
    if "stock" in t or "shareaward" in t or "equityaward" in t:
        return "stock"
    if "bonus" in t:
        return "bonus"
    if "total" in t:  # e.g. "SEC Total"
        return "total"
    return None


TITLE_WORDS = {
    "chief", "officer", "president", "executive", "former", "vice", "chairman", "chair",
    "chairwoman", "director", "senior", "svp", "evp", "ceo", "cfo", "coo", "cto", "general",
    "counsel", "secretary", "treasurer", "head", "managing", "group", "interim", "and", "of",
    "the", "founder", "co-founder", "principal", "operating", "financial", "technology",
    "retired", "board", "lead", "global", "corporate", "segment", "business", "division",
}


def extract_name(text: str) -> str | None:
    """Pull a person's name from a 'Name and Principal Position' cell.
    Returns None for title-only continuation lines ('Officer of YUM')."""
    text = re.sub(r"\(\s*[a-z0-9]{1,3}\s*\)", " ", text, flags=re.I)
    toks = re.findall(r"[A-Za-z.'\u2019-]+", text)
    name = []
    for t in toks:
        if t.lower().strip(".,") in TITLE_WORDS:
            break
        name.append(t)
    if not name or len(name) > 5:
        return None
    if name[0][0].islower():
        return None
    return " ".join(name)


def _value(tok: str) -> float | None:
    """Parse a numeric cell. Dashes/blank-ish markers mean zero."""
    tok = tok.replace("$", "").strip()
    tok = re.sub(r"(\(\s*[a-z0-9]{1,2}\s*\))+$", "", tok, flags=re.I).strip()  # trailing footnotes
    tok = tok.rstrip("*").strip()
    if not tok:
        return None
    if DASH_RE.match(tok) or tok.lower() in {"n/a", "nil"}:
        return 0.0
    neg = tok.startswith("(") and tok.endswith(")")
    tok = tok.strip("()").replace(",", "").strip()
    try:
        v = float(tok)
    except ValueError:
        return None
    return -v if neg else v


def _row_cells(tr) -> list[str]:
    for sup in tr.iter("sup"):
        # superscript footnote markers would otherwise glue onto numbers
        sup.text = " " + (sup.text or "") + " " if sup.text and len(sup.text.strip()) <= 3 else sup.text
    for br in tr.iter("br"):
        # stacked values ("2025<br>2024") must stay separate tokens
        br.tail = " " + (br.tail or "")
    return [_clean(td.text_content()) for td in tr if td.tag in ("td", "th")]


@dataclass
class SCTRow:
    name: str
    year: int
    values: dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return self.values.get("total", float("nan"))

    def component_sum(self) -> float:
        return sum(self.values.get(c, 0.0) for c in COMPONENTS)

    def reconciles(self) -> bool:
        tot = self.total
        if not tot or tot != tot:
            return False
        return abs(self.component_sum() - tot) <= max(0.01 * abs(tot), 10_000)


def _is_candidate(text: str) -> bool:
    t = re.sub(r"[^a-z]", "", text.lower())
    if not ("salary" in t and "total" in t):
        return False
    if not (("stock" in t or "option" in t or "equity" in t or "share" in t) and "award" in t):
        return False
    bad = ("feesearned", "actuallypaid", "threshold", "exercisable")
    return not any(b in t for b in bad)


def parse_table(table) -> list[SCTRow]:
    rows = table.findall(".//tr")
    cells = [_row_cells(r) for r in rows]
    # header = rows before the first row containing a standalone year
    first_data = None
    for i, cs in enumerate(cells):
        if any(YEAR_RE.match(c) for c in cs if c):
            first_data = i
            break
    if first_data is None or first_data == 0:
        return []
    # choose the header row that classifies the most labels; if the header is
    # split across rows, merge rows column-wise as a fallback
    best: list[str] = []
    for cs in cells[:first_data]:
        cats = [classify_header(c) for c in cs if c and not FOOTNOTE_RE.match(c) and c != "($)" and c != "$"]
        cats = [c for c in cats if c]
        if len(cats) > len(best):
            best = cats
    header = [c for c in best if c not in ("name", "year")]
    # de-duplicate consecutive identical categories (spanning labels)
    dedup: list[str] = []
    for c in header:
        if not dedup or dedup[-1] != c:
            dedup.append(c)
    header = dedup
    if "total" not in header or len(header) < 3:
        return []

    out: list[SCTRow] = []
    current_name = ""
    for cs in cells[first_data:]:
        toks = [c for c in cs if c and c not in ("$", "($)") and not FOOTNOTE_RE.match(c)]
        if not toks:
            continue
        year_idx = next((i for i, t in enumerate(toks) if YEAR_RE.match(t)), None)
        if year_idx is None:
            # a name/title-only row
            if any(re.search(r"[A-Za-z]{3,}", t) for t in toks) and not any(_value(t) not in (None,) for t in toks):
                current_name = extract_name(toks[0]) or current_name
            continue
        before = [t for t in toks[:year_idx] if re.search(r"[A-Za-z]{2,}", t)]
        if before:
            current_name = extract_name(before[0]) or current_name
        year = int(YEAR_RE.match(toks[year_idx]).group(1))
        vals = [_value(t) for t in toks[year_idx + 1:]]
        vals = [v for v in vals if v is not None]
        if len(vals) != len(header):
            # tolerate a single trailing blank (e.g. empty bonus column omitted)
            if len(vals) == len(header) - 1 and header[-1] == "total":
                continue
            continue
        row = SCTRow(name=current_name, year=year, values=dict(zip(header, vals)))
        out.append(row)
    return out


MULTI_YEAR_RE = re.compile(r"^(20[0-3]\d)(?:\s+20[0-3]\d)+$")


def _grid(table) -> list[list[dict]]:
    """Expand a table into a rectangular grid honouring rowspan/colspan.

    Each slot is ``{"text", "origin"}``; ``origin`` is True only for the
    left-most column a cell occupies (so a value spanning two columns is
    counted once), while headers are replicated across their span.
    """
    grid: list[list[dict]] = []
    carry: dict[int, tuple[dict, int]] = {}  # col -> (slot, rows_remaining)
    for tr in table.findall(".//tr"):
        row: list[dict] = []
        col = 0
        cells = [td for td in tr if td.tag in ("td", "th")]
        texts = _row_cells(tr)
        it = iter(zip(cells, texts))
        pending = True
        while pending:
            while col in carry:
                slot, left = carry[col]
                row.append({**slot, "origin": slot["origin"]})
                if left <= 1:
                    del carry[col]
                else:
                    carry[col] = (slot, left - 1)
                col += 1
            try:
                td, text = next(it)
            except StopIteration:
                pending = False
                break
            try:
                cs = max(1, min(int(td.get("colspan", 1)), 50))
                rs = max(1, min(int(td.get("rowspan", 1)), 50))
            except ValueError:
                cs, rs = 1, 1
            for k in range(cs):
                slot = {"text": text, "origin": k == 0}
                row.append(slot)
                if rs > 1:
                    carry[col] = (slot, rs - 1)
                col += 1
        grid.append(row)
    width = max((len(r) for r in grid), default=0)
    for r in grid:
        r.extend({"text": "", "origin": False} for _ in range(width - len(r)))
    return grid


def _split_multi(text: str, k: int) -> list[str] | None:
    text = re.sub(r"\$\s+", "$", text)
    parts = [p for p in text.split(" ") if p and p != "$" and not FOOTNOTE_RE.match(p)]
    if len(parts) == k:
        return parts
    if len(parts) == 1 and _value(parts[0]) == 0:
        return parts * k
    return None


def parse_table_grid(table) -> list[SCTRow]:
    grid = _grid(table)
    if not grid:
        return []
    first_data = None
    for i, r in enumerate(grid):
        if any(YEAR_RE.match(s["text"]) or MULTI_YEAR_RE.match(s["text"]) for s in r if s["origin"]):
            first_data = i
            break
    if not first_data:
        return []
    width = len(grid[0])
    labels = []
    for c in range(width):
        parts = []
        for r in grid[:first_data]:
            t = r[c]["text"]
            if t and t not in parts:
                parts.append(t)
        labels.append(" ".join(parts))
    cats = [classify_header(lbl) if lbl else None for lbl in labels]
    if "total" not in cats:
        return []

    out: list[SCTRow] = []
    current_name = ""
    for r in grid[first_data:]:
        ycol = next((c for c in range(width) if r[c]["origin"] and
                     (YEAR_RE.match(r[c]["text"]) or MULTI_YEAR_RE.match(r[c]["text"]))), None)
        if ycol is None:
            txt = [s["text"] for s in r if s["origin"] and s["text"]]
            if txt and re.search(r"[A-Za-z]{3,}", txt[0]) and all(_value(t) is None for t in txt):
                current_name = extract_name(txt[0]) or current_name
            continue
        left = [r[c]["text"] for c in range(ycol) if r[c]["text"] and re.search(r"[A-Za-z]{2,}", r[c]["text"])]
        if left:
            nm = extract_name(left[0])
            if nm:
                current_name = nm
        ytext = r[ycol]["text"]
        years = [int(y) for y in re.findall(r"20[0-3]\d", ytext)] if MULTI_YEAR_RE.match(ytext) \
            else [int(YEAR_RE.match(ytext).group(1))]
        k = len(years)
        per_year: list[dict[str, list[tuple[str, float]]]] = [{} for _ in range(k)]
        ok = True
        for c in range(ycol + 1, width):
            slot = r[c]
            if not slot["origin"] or not slot["text"] or cats[c] in (None, "name", "year"):
                continue
            if FOOTNOTE_RE.match(slot["text"]) or slot["text"] in ("$", "($)"):
                continue
            toks = [slot["text"]] if k == 1 else _split_multi(slot["text"], k)
            if toks is None:
                ok = False
                break
            for j, tok in enumerate(toks):
                v = _value(tok)
                if v is not None:
                    per_year[j].setdefault(cats[c], []).append((labels[c], v))
        if not ok:
            continue
        for j, y in enumerate(years):
            vals: dict[str, float] = {}
            for cat, items in per_year[j].items():
                if len(items) == 1:
                    vals[cat] = items[0][1]
                else:  # sub-columns: prefer an explicit subtotal, else sum
                    sub = [v for lbl, v in items if re.search(r"\btotal\b", lbl.lower().split(cat)[-1] if cat in lbl.lower() else lbl.lower())]
                    vals[cat] = sub[-1] if sub and cat != "total" else (items[-1][1] if cat == "total" else sum(v for _, v in items))
            if "total" in vals:
                out.append(SCTRow(name=current_name, year=y, values=vals))
    return out


def parse_sct(html: str) -> list[SCTRow]:
    """Return every reconciling row from all SCT-like tables, in document order.

    Each candidate table is parsed with the grid method first and the
    sequence method second; only rows whose components sum to the total
    survive. Duplicate rows (same year and total) are collapsed.
    """
    try:
        doc = lxml.html.fromstring(html.encode("utf-8", errors="replace"))
    except Exception:
        return []
    rows: list[SCTRow] = []
    seen: set[tuple[int, float]] = set()
    for t in doc.iter("table"):
        txt = t.text_content()
        if len(txt) > 40_000 or not _is_candidate(txt):
            continue
        for parser in (parse_table_grid, parse_table):
            try:
                parsed = parser(t)
            except Exception:
                parsed = []
            for r in parsed:
                key = (r.year, round(r.total))
                if r.reconciles() and key not in seen:
                    seen.add(key)
                    rows.append(r)
    return rows


def match_ceo_rows(rows: list[SCTRow], peo_totals: dict[int, float],
                   tol: float = 0.005) -> dict[int, SCTRow]:
    """Map fiscal year -> SCT row whose Total equals the XBRL PEO total.

    The SCT labels years by the company's own convention, which may differ by
    one from our Compustat-style FY label, so totals (not years) drive the
    match; the year only breaks ties.
    """
    out: dict[int, SCTRow] = {}
    for fy, target in peo_totals.items():
        if not target or target != target:
            continue
        hits = [r for r in rows if abs(r.total - target) <= tol * abs(target)]
        if hits:
            hits.sort(key=lambda r: abs(r.year - fy))
            out[fy] = hits[0]
    return out


def first_person_rows(rows: list[SCTRow]) -> list[SCTRow]:
    """Fallback (no XBRL): the first person listed in the SCT is the PEO by
    Item 402 convention."""
    if not rows:
        return []
    name = rows[0].name
    return [r for r in rows if r.name == name]
