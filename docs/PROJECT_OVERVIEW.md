# Project overview: CEO Pay vs. Performance

This page answers the seven questions the assignment asks every group to make clear. Each answer points to the evidence.

## 1. What we built

An AI-built research system that answers three investment questions from primary SEC data:
1. Does CEO pay track total shareholder return (TSR)?
2. Who are the biggest outliers, and why?
3. Does "overpay" predict future stock returns?

| Deliverable | Where |
|---|---|
| One-command data pipeline: SEC EDGAR → verified dataset → statistics → report | `src/`, run `python -m src.pipeline` |
| Interactive screener with a fact-checked AI analyst | `output/screener/index.html` (live version on claude.ai) |
| 5-page equity-research report with sourced case studies, plus a replication appendix | `output/report/report.pdf` |
| Strategy test (point-in-time quintile portfolios, CAPM abnormal returns) | `src/strategy.py`, chart `07_strategy_test.png` |
| Portfolio backtest (daily long-short, Sharpe, drawdown, CAPM alpha with Newey-West t-stats) | `src/backtest.py`, chart `08_backtest.png` |
| Full S&P 500 replication (all 500 companies, same code) | `FULL_UNIVERSE=1 python -m src.pipeline`, `src/replication.py`, chart `09_replication.png` |
| Validation suite and unit tests | `src/validate.py`, `output/validation/validation_report.md`, `tests/` |
| Presentation deck with speaker notes | claude.ai Slides artifact |
| Notebook walkthrough (runs offline) | `notebooks/analysis.ipynb` |

## 2. What problem it solves

CEO pay is the main tool boards use against the **agency problem**, and shareholders vote on it every year (say-on-pay). Since 2023 the SEC has required a pay-versus-performance table in machine-readable form, but almost nobody checks it at scale.

An analyst or a fund voting its proxies wants answers to three questions:
- Is this CEO's pay in line with peers of the same size and performance?
- If not, why not?
- Should I care as an investor?

Today that means reading 300-page proxies one at a time. Our system answers all three for 100 companies in about three minutes, with every number traceable to its filing.

## 3. How it works

1. **Collect.** We take each company's latest proxy XBRL (CEO pay, "compensation actually paid", TSR), its proxy HTML (pay mix) and its 8-K filings (say-on-pay votes) from SEC EDGAR, plus prices and dividends from Yahoo Finance.
2. **Parse and reconcile.** A pay-mix row is kept only if its components sum to its total *and* that total equals the XBRL figure. Multi-CEO years are handled per person, and the year-end CEO is used.
3. **Recompute.** TSR is rebuilt independently, with dividends reinvested, and compared with the company's own figure.
4. **Analyze:**
   - Model: `ln(3-yr avg pay) = a + b·TSR + c·ln(start-of-window market cap) + sector`, OLS with robust errors.
   - Outliers are the residuals from that model.
   - Pay mix is tested against TSR, and say-on-pay against excess pay.
   - Strategy test: quintiles on excess pay, scored by later CAPM abnormal returns.
   - Backtest: a daily long-underpaid / short-overpaid portfolio, rebalanced each 30 September, with Sharpe ratio, drawdown and CAPM alpha.
   - Replication: the whole pipeline is rerun on all 500 index members to check the 100-company results hold.
5. **Validate.** Nine automated checks plus 15 unit tests (section 6).
6. **Deliver.** The report, charts, screener and deck are all rendered from `output/results.json`, so text and numbers cannot drift apart.

## 4. How AI was used

Claude Code (an AI coding agent) wrote, ran and debugged the pipeline. Claude with web search found news and academic context. Claude drafted the report and slides from the results file. In the screener, Claude explains a company to the user.

AI is **never the source of a number**. Every figure comes from code running on SEC filings and market prices. Our group made every design decision; they are logged in `ASSUMPTIONS.md`. We also reviewed every chart and claim, and corrected the AI where it was wrong.

Full detail: [`AI_USAGE_AND_QC.md`](AI_USAGE_AND_QC.md).

## 5. What the output looks like

Headline results (99 companies, latest 3 fiscal years):

| Finding | Number |
|---|---|
| Share of granted-pay variation explained by TSR | 0.5% (+1.8% pay per +10 pts TSR, p = 0.69) |
| Share of realised-pay (CAP) variation explained by TSR | 46% (+58% per +10 pts, p < 0.001) |
| Rank correlation of granted pay with size vs with TSR | 0.55 vs 0.15 |
| Biggest above-model pay | Ares +244%, Palo Alto +222%, Booking +179%, all with 37–51%/yr TSR |
| Biggest below-model pay | Amazon −93%, Palantir −72%, Coinbase −57% (founders or lumpy grants) |
| Say-on-pay vs excess pay | Spearman −0.30 (p = 0.004); 3 failed votes in 247 meetings |
| Excess pay → later abnormal return | rank IC +0.03 in both cohorts (no signal) |
| Long underpaid / short overpaid backtest | CAPM alpha −1.8%/yr (t = −0.22); Sharpe −0.49 |
| **Full S&P 500 replication (481 companies)** | Granted-pay R² 0.9%, realised 42%; a small granted-pay link becomes detectable (+6.1% per 10 pts, p = 0.03); say-on-pay ρ −0.30; strategy IC +0.01/+0.02; backtest alpha −0.4%/yr |
| Proxy TSR filing errors found | 12 of 100 companies |

See the charts in `output/charts/` and the screener.

## 6. How we know the output is valid

| Check | Result |
|---|---|
| XBRL CEO pay appears verbatim in the human-readable proxy | 100/100 companies |
| Pay-mix rows reconcile (sum = total, total = XBRL) | 301/301 |
| Our TSR vs the proxy's TSR | median gap 0.07 pts; 12 companies' errors diagnosed |
| Case-study facts found in the cited SEC filing | 27/27 |
| Say-on-pay results vs each company's own description in its next proxy | 57/57 agree (median gap 0.1 pts) |
| Regression re-estimated in plain numpy | identical coefficients |
| Permutation test (2,000 shuffles) | granted pay p = 0.52, CAP p < 0.001 |
| Bootstrap 95% CI (granted pay, +10 pts TSR) | −4.3% to +11.7% (includes zero) |
| Leave-one-out | 0 of 99 drops change the conclusion |
| Unit tests from real filing layouts | 15/15 pass |
| Cold re-run from an empty cache | every dataset and result reproduced exactly |
| Same checks on the full index | 492/492 source match (488 verbatim, 4 within the filer's rounding); 1,410/1,410 pay-mix rows; 274/295 votes vs self-reports, with the gaps spot-checked by hand |

We also log **27 real errors** we caught and fixed during the build in `AI_USAGE_AND_QC.md`. They include a parser that first matched only 33% of companies, a 6% say-on-pay figure that was a parsing error, a chart drawn in the wrong units, a "+94-point" strategy signal that turned out to be one stock, and a frequency vote misread as a say-on-pay result (caught by check 9).

## 7. Why someone should care

- **Investors voting on pay.** The system flags packages that are far from the size and sector norm, then shows whether the cause is a one-time award, grant timing or a genuine pay-level choice. Shareholders already punish the *level* of pay (lower say-on-pay support), not weak returns.
- **Analysts.** Companies' own pay-versus-performance TSR figures contain errors in 12% of our sample, so check them before using them.
- **Anyone using AI for research.** It shows how to let AI build quickly while making every number prove itself: source matching, reconciliation, independent recomputation, statistical placebo tests, claim verification, and a live fact-checker on the AI's own answers.
