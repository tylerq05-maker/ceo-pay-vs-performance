# Check-in 2: Progress

*Talking points for the second meeting. Each heading is a question the assignment says to be ready for.*

## What we have built so far

- **Full pipeline from SEC filings to results.** It runs with one command, takes about 3 minutes from an empty cache, and covers 100 companies and 496 CEO-years.
- **Verified dataset.** CEO pay and "compensation actually paid" come from XBRL. The pay mix comes from the Summary Compensation Table and reconciles 301 of 301 rows. TSR is rebuilt independently. Say-on-pay covers 248 votes.
- **Statistics.** Regressions over 1-, 3- and 5-year windows with robustness checks, outliers from residuals, a within-company panel, pay mix, and say-on-pay.
- **Strategy test.** Point-in-time portfolios with CAPM abnormal returns.
- **Validation suite.** 8 automated checks plus 11 unit tests.
- **Deliverables.** Report, charts, notebook, an interactive screener with a fact-checked AI analyst, and the deck.

## What is working

- **Data coverage.** 100/100 companies have pay-versus-performance XBRL and a reconciled pay mix.
- **TSR agreement.** Our TSR matches the proxies to a median 0.07 points, and the gaps we found turned out to be the companies' own filing errors.
- **Clear headline.** Granted pay barely tracks TSR (R² 0.5%). Realised pay tracks it strongly (R² 46%). Size matters more than returns.
- **Explained outliers.** Every top outlier has a documented explanation verified in its filing.

## What is not working, or was weaker than hoped

- **First parser.** It matched the pay mix for only 33% of companies. It took five rounds of fixes to reach 100%.
- **Say-on-pay parser.** Its first version misread some filings; one showed 6% support. It now covers 90 of 100 companies; 10 layouts are still not handled.
- **No strategy signal.** The test found nothing. Raw averages looked like a strong signal until we traced it to one stock.
- **Outlier list.** The top "overpaid" companies are all strong performers, which is less intuitive than expected.

## What we changed from the original plan

- **Independent TSR became the analysis variable**, after the cross-check found errors in 12 companies' proxy figures.
- **We added a misalignment screen** (high pay plus weak returns) next to the regression outliers, because the outliers alone mostly measure pay relative to size.
- **We moved to outlier-robust statistics** (medians, rank tests) in the strategy test.
- **We added the screener's AI fact-checker**, so the AI's answers are checked automatically, not just generated.

## What still needs to be done before presentation day

- Tailor the "course concepts" slide to our syllabus terms.
- Each member rehearses one section using `DEFENSE_GUIDE.md`.
- Share the screener and deck links with the class.
- Optional: run the full 500-company universe (`FULL_UNIVERSE=1`) for a robustness slide.
