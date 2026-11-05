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
