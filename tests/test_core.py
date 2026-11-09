"""Known-answer tests for the logic most likely to go wrong.

Each fixture reproduces a real layout or tagging pattern found in the sample
(Apple's rowspan SCT, Starbucks' stacked years, Allstate's extra total column,
Starbucks/Boeing multi-CEO XBRL, Trane's duplicate members, Allstate's
cumulative TSR contexts, Citizens' and Palantir's 8-K layouts).
Run:  python -m pytest -q
"""
from datetime import date

import pandas as pd
import pytest

from src import pvp_xbrl, sct_parser
from src.market_data import total_return_index, tsr_between
from src.outlier_evidence import _doc_text, parse_say_on_pay


# --------------------------------------------------------------------------- SCT
APPLE_STYLE = """<table>
<tr><td>Name and Principal Position</td><td></td><td>Year</td><td></td><td>Salary ($)</td><td></td>
<td>Stock Awards<sup>(1)</sup> ($)</td><td></td><td>Non-Equity Incentive Plan Compensation ($)</td><td></td>
<td>All Other Compensation ($)</td><td></td><td></td><td>Total ($)</td></tr>
<tr><td rowspan="3">Tim Cook Chief Executive Officer</td><td></td><td>2025</td><td></td><td>3,000,000</td><td></td>
<td>57,535,293</td><td></td><td>12,000,000</td><td></td><td>1,759,518</td><td>(3)(4)</td><td></td><td>74,294,811</td></tr>
<tr><td></td><td>2024</td><td></td><td>3,000,000</td><td></td><td>58,088,946</td><td></td><td>12,000,000</td><td></td>
<td>1,520,856</td><td></td><td></td><td>74,609,802</td></tr>
<tr><td></td><td>2023</td><td></td><td>3,000,000</td><td></td><td>46,970,283</td><td></td><td>10,713,450</td><td></td>
<td>2,526,112</td><td></td><td></td><td>63,209,845</td></tr>
</table>"""

STACKED_YEARS = """<table>
<tr><td>Name and Principal Position</td><td>Year</td><td>Salary ($)</td><td>Bonus ($)</td><td>Stock Awards ($)</td>
<td>Non-Equity Incentive Plan Compensation ($)</td><td>All Other Compensation ($)</td><td>Total ($)</td></tr>
<tr><td>Brian Niccol chairman and chief executive officer</td><td>2025<br>2024</td><td>$1,599,998<br>$61,538</td>
<td>$5,000,000<br>$5,000,000</td><td>$19,881,585<br>$90,291,772</td><td>$1,971,000<br>$30,295</td>
<td>$2,540,190<br>$418,071</td><td>$30,992,773<br>$95,801,676</td></tr>
</table>"""

EXTRA_TOTAL = """<table>
<tr><td>Name and Principal Position</td><td>Year</td><td>Salary ($)</td><td>Bonus ($)</td><td>Stock Awards ($)</td>
<td>Option Awards ($)</td><td>Non-Equity Incentive Plan Compensation ($)</td>
<td>Change in Pension Value and Nonqualified Deferred Compensation Earnings ($)</td>
<td>All Other Compensation ($)</td><td>Total ($)</td><td>Total Without Change in Pension Value ($)</td></tr>
<tr><td>Jim Fitterling</td><td>2025</td><td>1,695,200</td><td>-</td><td>11,910,628</td><td>2,970,005</td>
<td>533,988</td><td>1,431,266</td><td>537,690</td><td>19,078,777</td><td>17,647,511</td></tr>
</table>"""


def test_sct_rowspan_layout():
    rows = sct_parser.parse_sct(APPLE_STYLE)
    by_year = {r.year: r for r in rows}
    assert set(by_year) == {2023, 2024, 2025}
    r = by_year[2025]
    assert r.name == "Tim Cook"
    assert r.values["stock"] == 57_535_293 and r.total == 74_294_811
    assert all(x.reconciles() for x in rows)


def test_sct_stacked_years_in_one_cell():
    rows = {r.year: r for r in sct_parser.parse_sct(STACKED_YEARS)}
    assert rows[2024].values["stock"] == 90_291_772
    assert rows[2025].total == 30_992_773


def test_sct_ignores_total_without_pension_column():
    (r,) = sct_parser.parse_sct(EXTRA_TOTAL)
    assert r.total == 19_078_777            # the real total, not 17,647,511
    assert r.values["pension"] == 1_431_266  # not mistaken for a pension value
    assert r.values["bonus"] == 0           # "-" means zero


def test_match_ceo_rows_uses_xbrl_total():
    rows = sct_parser.parse_sct(APPLE_STYLE)
    matched = sct_parser.match_ceo_rows(rows, {2025: 74_294_811, 2024: 74_609_802, 2022: 99_420_097})
    assert set(matched) == {2024, 2025}     # 2022 is not in the table -> no false match


def test_name_extraction_skips_title_lines():
    assert sct_parser.extract_name("Tim Cook Chief Executive Officer") == "Tim Cook"
    assert sct_parser.extract_name("Former Chief Executive") is None
    assert sct_parser.extract_name("Kevin Johnson(1)") == "Kevin Johnson"


# --------------------------------------------------------------------------- PvP XBRL
def _instance(peo_facts: str, contexts: str) -> bytes:
    return f"""<?xml version="1.0"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:ecd="http://xbrl.sec.gov/ecd/2024" xmlns:co="http://example.com/co">
{contexts}
{peo_facts}
</xbrl>""".encode()


def _ctx(cid, start, end, member=None):
    seg = (f"<segment><xbrldi:explicitMember dimension='ecd:IndividualAxis'>{member}</xbrldi:explicitMember></segment>"
           if member else "")
    return (f"<context id='{cid}'><entity><identifier scheme='http://www.sec.gov/CIK'>1</identifier>{seg}</entity>"
            f"<period><startDate>{start}</startDate><endDate>{end}</endDate></period></context>")


def test_pvp_multi_ceo_incumbent_and_cumulative_tsr():
    ctx = "".join([
        _ctx("y1", "2023-01-01", "2023-12-31"), _ctx("y2", "2024-01-01", "2024-12-31"),
        _ctx("y1a", "2023-01-01", "2023-12-31", "co:OldCeoMember"),
        _ctx("y2a", "2024-01-01", "2024-12-31", "co:OldCeoMember"),
        _ctx("y2b", "2024-01-01", "2024-12-31", "co:NewCeoMember"),
        _ctx("cum1", "2023-01-01", "2023-12-31"), _ctx("cum2", "2023-01-01", "2024-12-31"),
    ])
    facts = """
<ecd:PeoTotalCompAmt contextRef="y1a" unitRef="usd" decimals="0">10000000</ecd:PeoTotalCompAmt>
<ecd:PeoActuallyPaidCompAmt contextRef="y1a" unitRef="usd" decimals="0">12000000</ecd:PeoActuallyPaidCompAmt>
<ecd:PeoTotalCompAmt contextRef="y2a" unitRef="usd" decimals="0">4000000</ecd:PeoTotalCompAmt>
<ecd:PeoActuallyPaidCompAmt contextRef="y2a" unitRef="usd" decimals="0">3000000</ecd:PeoActuallyPaidCompAmt>
<ecd:PeoTotalCompAmt contextRef="y2b" unitRef="usd" decimals="0">25000000</ecd:PeoTotalCompAmt>
<ecd:PeoActuallyPaidCompAmt contextRef="y2b" unitRef="usd" decimals="0">20000000</ecd:PeoActuallyPaidCompAmt>
<ecd:PeoName contextRef="y1a">Old Ceo</ecd:PeoName>
<ecd:PeoName contextRef="y2a">Old Ceo</ecd:PeoName>
<ecd:PeoName contextRef="y2b">New Ceo</ecd:PeoName>
<ecd:TotalShareholderRtnAmt contextRef="cum1" unitRef="usd" decimals="2">110</ecd:TotalShareholderRtnAmt>
<ecd:TotalShareholderRtnAmt contextRef="cum2" unitRef="usd" decimals="2">99</ecd:TotalShareholderRtnAmt>
"""
    co, peo = pvp_xbrl.build_tables(pvp_xbrl.parse_instance(_instance(facts, ctx)))
    cy = pvp_xbrl.company_year_table(co, peo).set_index("fy")
    assert cy.loc[2024, "ceo_name"] == "New Ceo"          # newcomer is the year-end incumbent
    assert cy.loc[2024, "n_peos"] == 2 and bool(cy.loc[2024, "multi_peo_year"])
    assert cy.loc[2024, "seat_sct_total"] == 29_000_000
    assert cy.loc[2023, "tsr_value"] == 110 and cy.loc[2024, "tsr_value"] == 99   # cumulative contexts
    assert cy.loc[2024, "tsr_annual"] == pytest.approx(99 / 110 - 1)


def test_pvp_duplicate_members_collapse():
    ctx = "".join([_ctx("y", "2025-01-01", "2025-12-31"),
                   _ctx("a", "2025-01-01", "2025-12-31", "co:FirstPeoMember"),
                   _ctx("b", "2025-01-01", "2025-12-31", "co:SecondPeoMember")])
    facts = "".join(f'<ecd:PeoTotalCompAmt contextRef="{c}" unitRef="usd" decimals="0">27262157</ecd:PeoTotalCompAmt>'
                    f'<ecd:PeoActuallyPaidCompAmt contextRef="{c}" unitRef="usd" decimals="0">1000</ecd:PeoActuallyPaidCompAmt>'
                    for c in ("a", "b"))
    facts += '<ecd:TotalShareholderRtnAmt contextRef="y" unitRef="usd" decimals="2">120</ecd:TotalShareholderRtnAmt>'
    co, peo = pvp_xbrl.build_tables(pvp_xbrl.parse_instance(_instance(facts, ctx)))
    cy = pvp_xbrl.company_year_table(co, peo)
    assert int(cy["n_peos"].iloc[0]) == 1    # one CEO tagged twice, not two CEOs


def test_fiscal_year_label():
    assert pvp_xbrl.fiscal_year_label(date(2026, 1, 31)) == 2025
    assert pvp_xbrl.fiscal_year_label(date(2026, 6, 30)) == 2026
    assert pvp_xbrl.same_person("Robert KOrtberg", "Robert K. Ortberg")
    assert pvp_xbrl.same_person("Mr. Solomon", "David Solomon")


# --------------------------------------------------------------------------- TSR
def test_total_return_index_reinvests_dividends():
    px = pd.DataFrame({"date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
                       "close": [100.0, 98.0, 98.0], "dividends": [0.0, 2.0, 0.0]})
    tri = total_return_index(px)
    # price fell by exactly the dividend paid: total return must be zero
    assert tsr_between(tri, "2024-01-02", "2024-01-04") == pytest.approx(0.0)


# --------------------------------------------------------------------------- say-on-pay
CFG_STYLE = """<p>At the Annual Meeting, shareholders (i) elected all nominees, (ii) approved the advisory vote on
executive compensation, (iii) ratified Deloitte. There were 25,122,974 broker non-votes.</p>
<p>1. Election of Directors:</p><table><tr><td>Shares For</td><td>Shares Against</td><td>Shares Abstain</td></tr>
<tr><td>Lee Alexander</td><td>374,941,980</td><td>2,223,011</td><td>12,000</td></tr></table>
<p>2. Advisory vote on executive compensation:</p><table><tr><td>Shares For</td><td>Shares Against</td><td>Shares Abstain</td></tr>
<tr><td>221,556,645</td><td>155,322,032</td><td>575,757</td></tr></table>"""

PLTR_STYLE = """<p>Proposal 3 – Advisory Vote to Approve Named Executive Officer Compensation. The stockholders approved,
on an advisory basis, the compensation of the Company's named executive officers. The number of votes cast for and
against with respect to, Proposal 3 are set forth below:</p>
<table><tr><td>For</td><td>Against</td><td>Abstained</td><td>Broker Non-Votes</td></tr>
<tr><td>1,987,926,773</td><td>357,136,775</td><td>9,794,454</td><td>381,084,411</td></tr></table>
<p>Proposal 4 – Stockholder Proposal</p>"""


def test_say_on_pay_skips_intro_paragraph():
    res = parse_say_on_pay(_doc_text(CFG_STYLE))
    assert res["for"] == 221_556_645 and res["against"] == 155_322_032   # not the director row


def test_say_on_pay_own_proposal_number_not_a_delimiter():
    res = parse_say_on_pay(_doc_text(PLTR_STYLE))
    assert res["for"] == 1_987_926_773
    assert res["support"] == pytest.approx(1_987_926_773 / (1_987_926_773 + 357_136_775 + 9_794_454))


SOLV_STYLE = """<p>Proposal Number 3: shareholders voted on how often to cast future advisory votes on the compensation of
its named executive officers (every 1 year, 2 years, or 3 years).</p>
<table><tr><td>One Year</td><td>Two Years</td><td>Three Years</td><td>Abstentions</td><td>Broker Non-Votes</td></tr>
<tr><td>135,522,957</td><td>262,972</td><td>1,071,704</td><td>677,798</td><td>16,218,224</td></tr></table>
<p>Proposal Number 4: ratified PricewaterhouseCoopers.</p>"""


def test_say_on_pay_ignores_frequency_vote():
    # found by the validation cross-check: Solventum's frequency vote was read as say-on-pay
    assert parse_say_on_pay(_doc_text(SOLV_STYLE)) is None


def test_pay_scale_detects_thousands_tagging():
    """Devon Energy tagged its pay-versus-performance figures in $ thousands."""
    import pandas as pd
    from src import pvp_xbrl
    co = pd.DataFrame({"fy": [2023, 2024], "nonpeo_avg_sct": [5502.0, 6194.0], "nonpeo_avg_cap": [1204.0, 2599.0],
                       "nodim_sct_total": [14883.0, 17040.0], "nodim_cap": [814.0, 6709.0]})
    peo = pd.DataFrame({"fy": [2023, 2024], "sct_total": [14883.0, 17040.0], "cap": [814.0, 6709.0]})
    assert pvp_xbrl.pay_scale(co, peo) == 1000
    co2, peo2 = pvp_xbrl.rescale_pay(co, peo, 1000)
    assert peo2["sct_total"].tolist() == [14_883_000.0, 17_040_000.0]
    # A $1-salary founder CEO alongside normally paid officers is NOT rescaled.
    co["nonpeo_avg_sct"] = [12_866_150.0, 13_000_000.0]
    peo["sct_total"] = [2.75, 2.75]
    assert pvp_xbrl.pay_scale(co, peo) == 1


def test_ceo_pay_fill_rules():
    """J.B. Hunt tags SCT without a dimension; Tesla leaves $0 years untagged."""
    co = pd.DataFrame({"fy": [2023, 2024, 2025], "tsr_value": [110.0, 120.0, 130.0],
                       "nodim_sct_total": [8_256_333.0, None, None], "nodim_cap": [12_654_140.0, None, None]})
    peo = pd.DataFrame({"fy": [2023, 2024, 2025], "member": ["A", "B", "B"], "peo_name": ["A", "B", "B"],
                        "sct_total": [None, None, 158_359_009_867.0], "cap": [12_654_140.0, 1.4e9, 1.0e10]})
    df = pvp_xbrl.company_year_table(co, peo).set_index("fy")
    assert df.loc[2023, "ceo_sct_total"] == 8_256_333.0          # undimensioned SCT is the sole CEO's
    assert df.loc[2024, "ceo_sct_total"] == 0.0                  # CAP tagged, SCT absent: a "—" row
    assert bool(df.loc[2024, "sct_zero_inferred"]) and not bool(df.loc[2023, "sct_zero_inferred"])
    assert df.loc[2025, "ceo_sct_total"] == 158_359_009_867.0


# Raymond James / Invesco style: broker non-votes stated in prose before the table.
RJF_STYLE = """<p>2. Advisory vote on executive compensation. Our shareholders approved, on an advisory, non-binding basis,
the compensation of our named executive officers by the affirmative vote of 89.39% of the votes cast. With respect to
this proposal, there were 25,755,179 broker non-votes. The table below sets forth the voting results.</p>
<table><tr><td>Votes Cast "For"</td><td>Votes Cast "Against"</td><td>Abstentions</td></tr>
<tr><td>149,425,883</td><td>17,719,175</td><td>554,928</td></tr></table>"""

# Con Edison style: an intro that lists the proposals, then "(b)" and the director table.
ED_STYLE = """<p>(a) At the Annual Meeting, stockholders voted to elect the members of its Board of Directors; to ratify the
appointment of its independent accountants; and to approve, on an advisory basis, named executive officer
compensation.</p><p>(b) The number of shares voted for or against each director were as shown in the following table.
Not included in such amounts were 51,610,187 shares that were broker non-votes.</p>
<table><tr><td>Name</td><td>For</td><td>Against</td><td>Abstain</td></tr>
<tr><td>A. Director</td><td>217,852,727</td><td>21,541,129</td><td>1,234,567</td></tr></table>
<p>(d) The number of shares voted for or against the advisory vote to approve named executive officer compensation:</p>
<table><tr><td>For</td><td>Against</td><td>Abstain</td></tr><tr><td>220,000,000</td><td>17,000,000</td><td>2,000,000</td></tr></table>"""


def test_say_on_pay_ignores_broker_non_votes_and_director_tables():
    r = parse_say_on_pay(_doc_text(RJF_STYLE))
    assert r["for"] == 149_425_883 and r["against"] == 17_719_175
    r = parse_say_on_pay(_doc_text(ED_STYLE))
    assert r["for"] == 220_000_000 and r["against"] == 17_000_000
