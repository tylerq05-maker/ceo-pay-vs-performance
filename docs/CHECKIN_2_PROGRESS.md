# Check-in 2: Progress

*Talking points for the second meeting. Each heading is a question the assignment says to be ready for.*

## What we have built so far

- **Full pipeline from SEC filings to results.** It runs with one command, takes about 3 minutes from an empty cache, and covers 100 companies and 496 CEO-years.
- **Verified dataset.** CEO pay and "compensation actually paid" come from XBRL. The pay mix comes from the Summary Compensation Table and reconciles 301 of 301 rows. TSR is rebuilt independently. Say-on-pay covers 247 meetings, and 57 of 57 vote results we could compare match what the companies say about themselves.
- **Statistics.** Regressions over 1-, 3- and 5-year windows with robustness checks, outliers from residuals, a within-company panel, pay mix, and say-on-pay.
- **Strategy test and backtest.** Point-in-time portfolios with CAPM abnormal returns, plus a daily long-short backtest with Sharpe ratio, drawdown and CAPM alpha (Newey-West t-stats).
- **Validation suite.** 9 automated checks plus 15 unit tests.
- **Full S&P 500 replication.** The same code rerun on all 500 index members.
- **Deliverables.** Report, charts, notebook, an interactive screener with a fact-checked AI analyst, and the deck.

## What is working

- **Data coverage.** 100/100 companies have pay-versus-performance XBRL and a reconciled pay mix.
- **TSR agreement.** Our TSR matches the proxies to a median 0.07 points, and the gaps we found turned out to be the companies' own filing errors.
- **Clear headline.** Granted pay barely tracks TSR (R² 0.5%). Realised pay tracks it strongly (R² 46%). Size matters more than returns.
- **Explained outliers.** Every top outlier has a documented explanation verified in its filing.
- **Full-index replication.** On 481 companies the pattern holds: TSR explains 0.9% of granted pay vs 42% of realised pay, say-on-pay vs excess pay is −0.30 again, and the strategy and backtest still find nothing. With more data a small granted-pay link (+6% per 10 points, p = 0.03) becomes detectable, which sharpens our wording from "no link" to "a weak link".

## What is not working, or was weaker than hoped

- **First parser.** It matched the pay mix for only 33% of companies. It took five rounds of fixes to reach 100%.
- **Say-on-pay parser.** Its first version misread some filings; one showed 6% support. It now covers 89 of 100 companies. Cross-checking it against the companies' own descriptions caught one more misread (a frequency vote read as say-on-pay), which we fixed and covered with a unit test.
- **No strategy signal.** The test found nothing. Raw averages looked like a strong signal until we traced it to one stock.
- **Outlier list.** The top "overpaid" companies are all strong performers, which is less intuitive than expected.
- **Yahoo Finance blocked company-info requests mid-run** on the 500-company version, leaving market caps blank. We switched to SEC share counts × price and checked them against Yahoo: 97 of 100 within 10%.

## What we changed from the original plan

- **Independent TSR became the analysis variable**, after the cross-check found errors in 12 companies' proxy figures.
- **We added a misalignment screen** (high pay plus weak returns) next to the regression outliers, because the outliers alone mostly measure pay relative to size.
- **We moved to outlier-robust statistics** (medians, rank tests) in the strategy test.
- **We added the screener's AI fact-checker**, so the AI's answers are checked automatically, not just generated.
- **We scaled from 100 to all 500 companies** as a replication. Doing so surfaced filing problems the sample never hit: thousands-scale tagging, untagged $0 years, and four 8-K layouts. Each is now handled and unit-tested.

## What still needs to be done before presentation day

- Tailor the "course concepts" slide to our syllabus terms.
- Each member rehearses one section using `DEFENSE_GUIDE.md`.
- Share the screener and deck links with the class.
