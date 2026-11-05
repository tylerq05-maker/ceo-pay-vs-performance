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
