# Assumptions & Decisions Log

Every judgment call made while building this project, grouped by phase.
Each entry states the decision, the reason, and its likely impact.

## General / setup

| # | Assumption / decision | Why | Impact |
|---|---|---|---|
| G1 | SEC User-Agent is `Tyler Quezada research your.email@example.com` (placeholder). Override with the `SEC_CONTACT_EMAIL` env var. | Brief asked for an e-mail placeholder; SEC requires a contact string. | None on results. Set a real address before heavy use. |
| G2 | SEC requests are throttled to 8 req/s (limit is 10). | Keeps a safety margin under SEC fair-access policy, including during retries. | Slightly slower first run; cached runs make no requests. |
| G3 | Every raw download (Wikipedia, SEC JSON, XBRL, proxy HTML, Yahoo prices) is cached under `data/raw/` and **not committed** (`.gitignore`). Processed outputs in `data/processed/` **are** committed. | Raw cache is hundreds of MB. Committing processed data lets the notebook run offline. | Fresh clones re-download raw data on the first pipeline run (~10 min for the 100-co sample). |
| G4 | "Today" for this project is 2026-11-05. Most recent proxies cover fiscal 2025 (filed spring 2026). | Session date. | Latest PvP tables cover FY2021-FY2025. |

## Phase 1 - Universe

| # | Assumption / decision | Why | Impact |
|---|---|---|---|
| U1 | Constituent list, GICS sector and CIK come from Wikipedia's *List of S&P 500 companies* (snapshot cached in `data/raw/universe`, saved to `data/processed/universe.csv`). | No free official S&P constituent feed. Wikipedia is maintained and widely used. | Could lag index changes by days. |
| U2 | CIKs cross-checked against SEC `company_tickers.json`; SEC wins on conflict. | SEC is the filer of record. | 0 mismatches on the current snapshot. |
| U3 | Dual-class companies (GOOGL/GOOG, FOXA/FOX, NWSA/NWS) are one company: keep the Class A ticker. | CEO pay is reported once per issuer (CIK). | 503 tickers become 500 companies. |
| U4 | Sample = 100 companies, **proportional allocation by GICS sector** (largest-remainder rounding, min 2 per sector), random within sector, seed 42. `FULL_UNIVERSE=1` runs all 500. | Brief: stratified 100-co sample, easy to scale. Random within sector avoids a large-cap bias. | Sector weights mirror the index. Results generalize with sampling error (n=100). |
| U5 | Survivorship: the sample is drawn from *current* constituents, then looks back 1-5 years. | Brief asks for current constituents. | Biases TSR upward (firms that crashed out of the index are excluded). Noted in report limitations. |

## Phase 2 - Compensation (SEC EDGAR)

| # | Assumption / decision | Why | Impact |
|---|---|---|---|
| C1 | Primary source is the PvP XBRL instance (`*_htm.xml`) of each company's **most recent DEF 14A filed since 2023 that contains `ecd:PeoTotalCompAmt`**. Special-meeting DEF 14As without a PvP table are skipped (up to 4 proxies tried). | The latest proxy holds the longest PvP history (up to 5 fiscal years). | 100/100 sample companies had PvP XBRL; the SCT-only fallback is implemented but not needed for this sample. |
| C2 | The SEC `frames`/`companyfacts` APIs are **not** used for PvP data. | They drop dimensional facts (per-CEO values in multi-CEO years) and keep only one value per period. | Requires one extra download per company, but captures CEO transitions correctly. |
| C3 | Fiscal-year label follows the Compustat convention: FY = calendar year of the period end if it ends in June or later, else the prior year (e.g. FYE 31-Jan-2026 = FY2025). | Puts retailers and January year-ends on the same footing as calendar filers. | Three companies' latest year is FY2026 (June-Sept 2026 year-ends); the rest are FY2025. |
| C4 | **Multiple PEOs in one year:** per-person facts on `ecd:IndividualAxis` are kept (`pvp_peo_rows.csv`). PEOs with zero SCT pay *and* zero CAP that year are treated as not serving. Members with identical values are collapsed (e.g. Trane tags one CEO as "First PEO" and "Second PEO"). | Several filers list every historical PEO in every year with zeros. | `multi_peo_year` flag; 35 companies have at least one multi-PEO year. |
| C5 | **The CEO for a year is the year-end incumbent**, chosen in this order: (1) the PEO who also appears in the next year; (2) otherwise the PEO absent from the prior year (the newcomer); (3) otherwise the highest-paid PEO. Name matching is punctuation-insensitive ("Robert KOrtberg" = "Robert K. Ortberg"). `seat_sct_total` / `seat_cap` (sum of all PEOs) are kept as alternatives. | Matches how most pay studies define "the CEO". Summing seats double-counts severance plus sign-on. | In transition years the incumbent's pay can be a partial year or include sign-on grants. Robustness check excludes these. |
| C6 | Missing `PeoName` tags are back-filled from the SCT row whose Total equals the XBRL PEO total. `PeoName` facts tagged as `NonPeoNeoMember` are ignored (Apple tags its other NEOs with `PeoName`). | Names are needed to identify incumbents and to flag CEO changes. | Cosmetic except for incumbent selection. 10 company-years still lack a tagged name. |
| C7 | Globe Life (GL) reports **co-CEOs** in every year. The first-listed co-CEO is used; flagged via `multi_peo_year`. | No single CEO exists. | Pay understates the CEO-seat cost by about half for GL. |
| C8 | TSR facts are matched to fiscal years by **period end date**, whatever the context duration. Some filers use one-year contexts and others use cumulative base-to-year-end contexts. | Both conventions appear in the sample. | Proxy TSR is now present for 99/100 companies (BLK's 2025 value is missing). |
| C9 | **XBRL tagging errors exist.** BlackRock tags its TSR values one year off their true dates. Starbucks reports `NetIncomeLoss` in millions. Net income is therefore not used, and proxy TSR serves as a *cross-check* while independently computed TSR is the analysis variable (see M-section). | Data quality. | Discrepancies are flagged in `tsr_crosscheck.csv`. |
| C10 | **Pay mix** comes from the Summary Compensation Table in the same proxy's HTML. A row is accepted only if (a) its components sum to its Total within 1% or $10k **and** (b) its Total equals the XBRL PEO total for that year within 0.5%. Components: salary, bonus, stock awards, option awards, non-equity incentive (cash bonus plan), pension/NQDC change, all other. | Proxy HTML layouts vary widely; double reconciliation means no unverified number enters the dataset. | Pay mix reconciled for 100/100 companies (301 CEO-years; usually the 3 most recent years). |
| C11 | SCT values are grant-date fair values (what the board *awarded*). CAP marks equity to market (what the CEO *realized on paper*). Both are analysed separately and never mixed. | They answer different questions. | See report methodology. |

## Phase 3 - Market data

| # | Assumption / decision | Why | Impact |
|---|---|---|---|
| M1 | Prices from Yahoo Finance via `yfinance` (daily, 2019-01-01 onward), cached to `data/raw/market/prices.csv.gz`. | Brief specifies yfinance. | Free data; occasional gaps. 100/100 tickers retrieved. |
| M2 | **Independent TSR** = total-return index built from split-adjusted close + cash dividends reinvested on the ex-date: `TRI_t = TRI_{t-1} x (Close_t + Div_t) / Close_{t-1}`. | Transparent, reproducible, and mirrors the SEC's PvP TSR definition (dividends reinvested). | Matches Yahoo's dividend-adjusted close to a median 0.02% over 5 years (`tsr_adjclose_check.csv`). |
| M3 | Prices are taken on the **last trading day on or before** each date (max 10-day lookback). | Fiscal years often end on weekends (52/53-week years). | Negligible. |
| M4 | **Pay windows follow each company's own fiscal calendar.** The N-year window ends at the latest PvP fiscal year end and starts the day before the first fiscal year in the window. Windows: 1, 3 (primary), 5 years. | Pay and performance must cover the same period; fiscal year ends differ (Jan, Apr, Jun, Sep, Dec). | Companies are compared over slightly different calendar windows (most end Dec-2025; a few end Jan-Jun 2026). |
| M5 | **Independent TSR is the analysis variable; proxy TSR is the cross-check.** A company-year is flagged when the two differ by more than 10 points on the $100-index scale. Each flag is diagnosed automatically as `stale_base` (earlier years still measured from the prior proxy's base date), `misdated` (values tagged one year early), or `other`. | The cross-check found systematic filing errors that would corrupt proxy-based multi-year returns. | 12 companies flagged: 10 stale-base, 1 misdated (BLK), and 2 with an unexplained year (MAS, ULTA). In 10 of the 12 the *latest-year* 5-year value still agrees within 0.1 points. Median gap across all 491 company-years is 0.07 points. |
| M6 | Trailing calendar TSR (1/3/5y to 2026-10-30) is computed for market context only and not used in regressions. | It does not line up with the pay period. | Context only. |
| M7 | **Size control = market cap at the start of the pay window**, approximated as `current market cap x (price at window start / current price)` using split-adjusted closes. | End-of-period market cap partly *is* the TSR (winners get bigger), which would soak up the effect being measured. | Ignores share-count changes (buybacks/issuance, typically 1-3%/yr), so it is off by roughly ±5-10% in level, small on a log scale. |
| M8 | Fundamentals (market cap, ROE, margins, revenue) come from `yfinance` `info` and the annual income statement. Revenue CAGR uses the ~4 years of annual statements Yahoo provides. ROE is trailing-twelve-month. | Context variables requested in the brief. | ROE missing for 13 companies (Yahoo omits it, e.g. negative equity). These are descriptive only, not regression controls. |
| M9 | Companies without enough history are excluded from that window: Coinbase (IPO 2021) has no 5y window, CRH (US primary listing) has no 5y window, and Solventum (spun off 2024) has no 3y or 5y window. | Can't compute TSR before listing. | Primary 3y sample n = 99. |

## Phase 4 - Analysis

| # | Assumption / decision | Why | Impact |
|---|---|---|---|
| A1 | **Unit of analysis = company.** Pay = average annual CEO pay over the window; TSR = annualised independent TSR over the *same* fiscal window. Primary window = 3 fiscal years (FY2023-FY2025 for most); 1y and 5y are robustness. | Averaging smooths lumpy grants. Three years matches the standard performance-share cycle and limits CEO-turnover noise. | n = 99 for 3y (Solventum lacks history), 100 for 1y, 97 for 5y. |
| A2 | Two pay measures, analysed separately: **SCT total** (grant-date value the board awarded) and **CAP** (compensation actually paid, which marks equity to market). | Brief asks for both; they answer different questions. | CAP is mechanically linked to stock price, so a strong CAP-TSR link is partly by construction. The report says so. |
| A3 | SCT pay is modelled in logs. CAP is modelled with **asinh(CAP in $M)** because CAP is negative in 40 CEO-years; asinh behaves like a log for large values and is defined for negatives. | Pay is heavily right-skewed. | CAP coefficients are approximate log-point effects. |
| A4 | TSR enters in **percentage points per year, winsorised at the 2.5th/97.5th percentiles** (3y bounds: -19.3% to +71.8%/yr). Raw-TSR and rank-rank regressions are reported as robustness. | Palantir's +203%/yr would otherwise dominate any linear fit. | Main conclusions hold with raw TSR. |
| A5 | OLS with **HC3 heteroskedasticity-robust standard errors**. Panel models use company and fiscal-year fixed effects with errors clustered by company. | Standard practice for small cross-sections with skewed data. | Conservative p-values. |
| A6 | **Size control = ln(market cap at window start)** (see M7). Sector = 11 GICS sector dummies. Robustness: current market cap, ln(revenue), no sector dummies. | Brief requires a size control. Start-of-window size avoids absorbing the TSR effect. | Size elasticity is about 0.15-0.18: doubling market cap means roughly 11-13% more pay. |
| A7 | **Outliers = residuals from the primary model** `ln(avg SCT pay, 3y) ~ TSR + ln(mcap) + sector FE`. Positive residual = "overpaid relative to performance (and size/sector)"; negative = "underpaid". Top/bottom 5 reported. Rank stability is checked under four alternative models (no sector FE, CAP-based, 5y window, model fitted without no-equity-grant companies). | Brief specifies regression residuals. | Because TSR explains little of granted pay, the residual mostly measures *pay relative to size and sector*. The top-5 "overpaid" all had strong TSR; this is a finding, discussed in the report. |
| A8 | A complementary **misalignment screen** lists positive-residual companies with *below-median* TSR (and the reverse). | Captures the intuitive "paid a lot, delivered little" case that pure residuals miss when the TSR slope is flat. | Omnicom tops it. Reported alongside the residual outliers, not instead of them. |
| A9 | Deep dives cover the **strict top 3 on each side** of the residual ranking (6 total, no cherry-picking), plus short notes on #4 overpaid (GS) and the #1 misalignment case (OMC). | Brief: "aim for 6"; strict ranking avoids selection bias. | |
| A10 | Robustness: companies with **no equity grant in the 3y window** (AMZN, COIN, META, PLTR; equity share <5% of SCT pay) are excluded in one specification. | Their CEOs' SCT pay is near-zero by design (founder or multi-year mega-grant), so they are high-leverage points. | Excluding them, the TSR slope becomes significant (+11.6% pay per +10 pp TSR, p=0.001). Reported transparently as a key nuance. |
| A11 | Pay mix uses reconciled SCT rows only, summed over the window's fiscal years (component $ / total $). Bonus = discretionary bonus column; "cash incentive" = bonus + non-equity incentive plan. | Weighted mix avoids small-year distortion. | 100/100 companies have at least one reconciled year (99 in the 3y model). |
| A12 | Sector-level correlations use Spearman's rho with n of 4-17 per sector. They are descriptive only, with low statistical power. | Small cells. | Shown in a chart with sample sizes; not over-interpreted. |

## Phase 5 - Outlier evidence

| # | Assumption / decision | Why | Impact |
|---|---|---|---|
| E1 | Say-on-pay results are parsed from each company's 8-K **Item 5.07** filings since 2024. Support = For / (For + Against + Abstain). Broker non-votes are excluded. | Primary source; the "votes cast" basis used by proxy advisers. Some companies report For/(For+Against), so company-quoted figures can differ by a few tenths of a point (e.g. Ares quotes 92.3%, we compute 92.2%). | Parsed for 90/100 companies (248 meetings). Low-support parses were spot-checked against the filing text. 10 companies' 8-K layouts were not parsed. |
| E2 | Say-on-pay support at **controlled companies** (Coinbase, Palantir, Ares; confirmed in each proxy) mainly reflects insider votes and is not read as outside-investor approval. | Founder/insider voting control. | Interpretation only. |
| E3 | Case-study facts not computed from our dataset (award sizes, vesting terms, vote outcomes) are quoted from the cited SEC filings first and news outlets second. Figures in news articles that we could not match to a filing are not used. | "Every number must trace back to the data." | Each case study lists its sources with links. |
| E4 | Proxy keyword snippets (`outlier_evidence.json`) are a research aid to find relevant CD&A passages, not an analytical input. | Speeds up reading 300-page proxies. | None on results. |

## Phase 6 - Deliverables

| # | Assumption / decision | Why | Impact |
|---|---|---|---|
| R1 | `report.md`/`report.pdf` and `README.md` are **rendered from `output/results.json` and processed CSVs** by `src/report.py`. No statistic is typed by hand. Filing facts (award sizes, vesting terms, board statements) are quoted with a link to the SEC filing or news article. | Brief: every number must trace to the data. | Re-running the pipeline on new data updates every figure consistently. |
| R2 | Case-study verdicts use three labels: *explained* (a documented structural or one-time cause), *no clear one-off reason* (a sustained pay-level choice, e.g. BKNG), and *not investigated in depth* (outlier-table rows outside the deep dives). | Brief: say explicitly when no clear reason exists. | |
| R3 | Charts are static PNGs (light theme) for print/PDF. The dataviz palette was validated for colour-vision deficiency. Their "table view" is the CSV set in `output/tables/`. | Report and README embed images. Interactivity does not apply to PDF. | |
| R4 | The LinkedIn graphic is 1080x1350 px (4:5 portrait, the largest feed format) and states its sample, sources and "correlation, not causation". | Standalone shareability. | |
| R5 | The notebook regenerates the analysis offline from committed processed data. `RUN_PIPELINE = True` re-downloads from source. | Runs top to bottom without network or credentials. | |

## Strategy test & validation (added for the class project)

| # | Assumption / decision | Why | Impact |
|---|---|---|---|
| S1 | **Point-in-time formation dates.** Cohort A (pay FY2021-23) forms 2024-09-30 and cohort B (pay FY2022-24) forms 2025-09-30, after every proxy for those years was filed. Positions are held to the last common price date. | Avoid look-ahead bias: the signal uses only information public at formation. | Holding periods are about 2.1 and 1.1 years. |
| S2 | The "excess pay" signal is the residual of the primary model **re-fitted on that cohort's window only**. | The model itself must not use future data. | The cohort A signal model has R² 0.49 (vs 0.19 for the latest window). |
| S3 | Earlier-year pay comes from the latest proxy, not the proxy filed at the time. | Simplicity; SCT totals are rarely restated. | Small look-ahead risk, documented. |
| S4 | Abnormal return = (R − Rf) − β(R_SPY − Rf). β comes from 104 weekly returns before formation; Rf compounds the 13-week T-bill (^IRX). | CAPM benchmark. | Raw, SPY-relative and sector-adjusted returns are also reported. |
| S5 | **Medians, 5/95% winsorized means, Mann-Whitney and rank IC are the primary statistics.** Raw means are shown but not relied on. | Single "moonshot" stocks (Bloom Energy +1,798%, Moderna +900%, both verified as real moves) dominate 19-stock equal-weighted means. | Conclusion: no predictive signal in either cohort. |
| V1 | The validation suite (`src/validate.py`) uses 2,000 permutations and 2,000 bootstrap draws (seed 11). | Distribution-free inference that does not rely on OLS assumptions. | Results are reproducible. |
| V2 | Claim verification uses regex matches against the cached text of the cited filing. A claim fails if its wording is not found. | Mechanical anti-hallucination check on every quoted filing fact. | 27/27 pass. |
