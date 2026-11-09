# How AI was used, and how we kept it honest

## 1. Where AI was used

| Role | Tool | What it did | What it did **not** do |
|---|---|---|---|
| Coding agent | Claude Code (Anthropic) | Wrote, ran and debugged the Python pipeline: SEC downloader, XBRL and HTML parsers, TSR engine, regressions, charts, report renderer, tests | Generate any number. Every figure comes from code running on SEC filings and market prices. |
| Research assistant | Claude with web search | Found news coverage and academic context for the outliers (e.g. Goldman's retention awards, Moderna's Aug-2026 jump, Cooper–Gulen–Rau) | Serve as the source of record. Facts used in the report are verified in the SEC filing itself (section 4). |
| Drafting | Claude | Drafted the report, README and slides from `results.json` | Type statistics by hand. The report is *rendered* from `results.json`, so text and data cannot drift apart. |
| In-app analyst (screener) | Claude via the artifact runtime | Explains one company's numbers in plain English | Act unchecked. Every number in its answer is automatically compared with the verified data and flagged if absent. |

**Our role (the humans):** we chose the question and the design. That covered:
- which pay measure to use, and why we report both SCT and CAP;
- the 3-year window, and how to treat CEO changes;
- winsorizing TSR, and size measured at the start of the window;
- which outliers to investigate.

We also reviewed every chart and paragraph, and we rejected or corrected the AI's output where it was wrong (section 3). The judgment calls are logged in [`ASSUMPTIONS.md`](../ASSUMPTIONS.md).

## 2. The quality-control stack

Each layer catches a different kind of error. All of them are automated and re-run with `python -m src.pipeline` or `python -m src.validate`.

| Layer | Question it answers | Mechanism | Result |
|---|---|---|---|
| Source | Is the raw number really in the filing? | XBRL CEO pay must appear verbatim in the proxy HTML | 100/100 companies (SCT and CAP) |
| Parse | Did the HTML parser read the right cells? | A pay-mix row is kept only if its components sum to its total **and** that total equals the XBRL figure | 301/301 rows reconcile |
| Independent recompute | Is the company-reported TSR right? | Rebuild TSR from prices and dividends; compare with every proxy year | Median gap 0.07 pts; 12 companies' filing errors caught and diagnosed |
| Cross-implementation | Is the regression code right? | Re-fit with plain numpy least squares | Coefficients identical to ~1e-16 |
| Statistical robustness | Is the result real or noise? | Permutation test (2,000 shuffles), bootstrap CI, leave-one-out, 8 alternative specifications | Granted-pay null and CAP effect both hold everywhere |
| Claim verification | Did the AI invent a fact? | Every filing fact in the case studies is regex-matched in the cited SEC document | 27/27 verified |
| Unit tests | Do parsers handle known edge cases? | 15 known-answer tests built from real layouts | 15/15 pass |
| Independent self-reports | Is our vote data right? | Our 8-K parse is compared with the support each company states in its next proxy | 57/57 agree (median gap 0.11 pts); found one real bug (#19) |
| Replication | Does it hold beyond the sample? | Same pipeline re-run on the full S&P 500 | See report appendix |
| Human review | Does it make sense? | Every chart was rendered and inspected, and every paragraph proofread against the data | 27 issues logged (below) |

## 3. Errors and weak results we caught

This is the real log from building the project. Most were caught because a number looked implausible, an independent check disagreed, or a chart looked wrong.

| # | Phase | What went wrong | How we caught it | Fix |
|---|---|---|---|---|
| 1 | XBRL parsing | A namespace typo (`xbrldi.org` instead of `xbrl.org/2006/xbrldi`) silently dropped every per-CEO fact | Starbucks showed several pay values in the same year with no CEO names | Corrected the namespace; added a multi-CEO unit test |
| 2 | XBRL parsing | Apple tags its *other* executives with the CEO-name tag, which would have mislabeled the CEO | Inspected the raw facts: 26 "CEO name" facts for one CEO | Ignore names tagged `NonPeoNeoMember` |
| 3 | XBRL parsing | Trane tagged one CEO twice ("First PEO"/"Second PEO"), doubling "CEO-seat" pay | Seat pay was exactly 2× the CEO's pay | Collapse members with identical values; unit test |
| 4 | XBRL parsing | TSR was missing for 37 company-years | Coverage audit | Some filers use cumulative date ranges; match TSR by period end date |
| 5 | CEO identity | YUM's 2025 CEO came out as the outgoing CEO (David Gibbs) instead of Chris Turner | Checked transition years against known CEO changes | Back-fill untagged names from the reconciled pay table before choosing the incumbent |
| 6 | HTML parsing | The pay-mix parser matched only **33 of 100** companies at first | Match-rate audit against the XBRL totals | Fixed whitespace ("StockAwards"), a "Total without pension" column, headerless "Year" columns, stacked years: 47 → 93 → **100** |
| 7 | HTML parsing | Stacked years separated only by `<br>` would merge ("20252024") | A unit test failed | Treat `<br>` as a separator; output unchanged (0 numeric differences) |
| 8 | Say-on-pay | Citizens Financial showed **6%** shareholder support, which is implausible | Sanity check on extreme values | The parser had read the director-election table; it now reads only within the proposal's own section. Spot-checked 6 filings by hand |
| 9 | Say-on-pay | Northern Trust parsed the "shares present" count as votes in favor | Same spot check | Off-by-offset bug in the section boundary |
| 10 | Proxy TSR | BlackRock's TSR differed from market data by up to 35 points | Independent TSR cross-check | Diagnosed as values tagged one year early (BlackRock's error, not ours) |
| 11 | Proxy TSR | 10 other companies' earlier-year TSR was wrong | Same cross-check | Diagnosed automatically as "stale base" (not restated). This became a finding |
| 12 | Filing error | Palantir reports 2024 CEO pay as $4,630,170 in one table and $4,360,170 in another | The double-reconciliation rule refused to match that year | Reported as a finding; verified in the filing text |
| 13 | Charts | The fitted line on the main scatter sat far above the data | Visual review | Model in ln(dollars), axis in $M: divide by 1e6 |
| 14 | Report | Several numbers were typed into the text template ("37–51%/yr", "10 of 11 sectors") instead of computed | Proofreading against `results.json` | All replaced with computed values; the report is now fully rendered from data |
| 15 | Over-claiming | Draft said "2× market cap ≈ +14% pay", but that coefficient had p = 0.19 | Checked the p-value behind every claim | Restated with the robust evidence (rank correlation 0.55 vs 0.15) |
| 16 | Over-claiming | Draft chart titles said "granted pay doesn't track returns in any sector" and "pay mix looks the same" | Compared titles with the data | Titles now computed from the data ("10 of 11 vs 3") and caveated |
| 17 | Strategy test | Overpaid quintile appeared to beat underpaid by **+94 pp**, which looked like a strong signal | Too good to be true, so we looked at individual stocks | One stock (Bloom Energy, +1,798%) drove it. Moderna's +900% was also checked and is real (Aug-2026 cancer-vaccine data). We switched to medians, winsorized means and rank tests: no signal |
| 18 | Interpretation | The top "overpaid" residuals were all strong performers, which could mislead | Read the outlier list critically | Added a misalignment screen (high pay + weak returns) and said so explicitly |
| 19 | Say-on-pay | Solventum's say-on-**frequency** vote ("One Year / Two Years / Three Years") was recorded as a 99% say-on-pay result | A new cross-check against the support each company reports in its own proxy (Solventum says about 85%) | The parser now rejects frequency tables, even when the word "frequency" never appears. Unit test added |
| 20 | Cross-checker | The first cross-checker raised 5 false alarms: it read a 10-year average, a "more than 90%" bound, another proposal's 93%, and board statistics | Read every flagged sentence in the filing | Only percentages described as vote support in the same sentence count. Result: 57/57 agree |
| 21 | Market data | Yahoo's quote service started refusing requests (HTTP 401) mid-run, and the code was about to cache "no market cap" for 400 companies | Coverage audit of the full-index run | Empty responses are never cached. The full index uses SEC-reported shares × price, which agrees with Yahoo within 10% for 97 of 100 sample companies |
| 22 | Full-index parsing | J.B. Hunt tags only one of the two CEO-pay concepts on the CEO, which crashed the parser | Error log of the 500-company run | Missing concepts are now handled, and the undimensioned figure fills a single-CEO year (ASSUMPTIONS F6) |
| 23 | Backtest | The long-short portfolio "lost 15%", which looked like the signal working in reverse | CAPM regression | Explained by beta: the overpaid fifth has beta 1.25 vs 0.85. Alpha is about zero (t = −0.22) |
| 24 | Full-index data | Devon Energy's CEO "earned $14,830" | Implausible-value check on the full-index outliers | Devon tagged the printed thousands. Thousands-scale filings are now detected and rescaled (ASSUMPTIONS F5), with a unit test |
| 25 | Full-index data | Tesla's 3-year average CEO pay came out at $158B, Musk's entire 2025 award | Read Tesla's Summary Compensation Table: 2021–24 show "—" ($0), and those cells were left untagged | A CAP-only year is now treated as $0 granted pay (ASSUMPTIONS F7), with a unit test |
| 26 | Full-index say-on-pay | Con Edison, Invesco and Raymond James showed 10–18% support; Everest 51% | Check 9 on the full index (cross-check against each company's own proxy) | The parser read broker non-vote counts and a director table as votes. Fixed, with 2 new unit tests; the sample is unchanged. Full-index agreement rose from 267/297 to 274/295. A spot-check of the remaining gaps found the checker reading a 10-year range or a prior year's figure (S&P Global, Seagate, Expedia: our parse matches the company's own words). Workday (dual-class, company states 86%, we parse 99%) is unresolved |
| 27 | Validation | Source match flagged Casey's, Northrop, Tesla and Xylem | Read the filings | They tagged rounded figures (Casey's: $14,741,000 tagged, $14,741,268 printed). The check now accepts a printed figure within the filer's own rounding and reports verbatim and rounded matches separately |

## 4. What we could not fully verify

- **News-only context.** For example, "seven rejected pay votes since 2015" for Palo Alto comes from Bloomberg via secondary coverage. It is cited, but we did not verify it ourselves.
- **Restated pay.** Earlier-year pay comes from the *latest* proxy. Companies rarely restate it, but the strategy test is therefore not perfectly point-in-time.
- **Market-cap approximation.** It ignores share buybacks (±5–10%); results are not sensitive to swapping in revenue.
- **Say-on-pay coverage.** Votes were parsed for 89 of 100 companies; the other 11 use layouts we did not handle. Missing is safer than wrong (see #19).
- **Survivorship bias.** The sample is today's S&P 500, so firms that collapsed and left the index are missing.
