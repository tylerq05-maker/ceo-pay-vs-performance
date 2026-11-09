# Check-in 1: Game plan

*Talking points for the first meeting. Each heading is a question the assignment says to be ready for.*

## Our idea

Use AI to build a research system that tests whether **S&P 500 CEO pay tracks shareholder returns**, finds the biggest outliers and explains them from the filings, and tests whether **"overpay" predicts future stock returns**.

## How it relates to investments

- **Corporate governance and agency theory.** Pay is the main tool for aligning managers with shareholders.
- **Stewardship.** Funds vote on pay every year (say-on-pay) and need evidence to vote well.
- **Return measurement.** Total shareholder return with dividends, CAPM abnormal returns.
- **Market efficiency.** Is a public signal (excess pay) priced, or does it predict returns?

## What the final result should do

1. Pull CEO pay and TSR for a sector-stratified sample of 100 S&P 500 companies straight from SEC filings, scalable to all 500.
2. Measure how much pay moves with returns, controlling for company size and sector.
3. Rank the companies paid most above and below what size, sector and returns predict, and explain the top cases with sources.
4. Test a trading signal: do the most "overpaid" companies underperform afterwards?
5. Deliver a report, charts, and an interactive screener an investor could use.

## AI tools we expect to use

- **Claude Code** (AI coding agent) to write and debug the data pipeline and analysis.
- **Claude with web search** for news and academic context on outliers.
- **Claude inside the screener** to explain a company in plain English, restricted to verified data.

## How we will make sure the output is not "slop"

- **AI is never the source of a number.** Every figure comes from code running on SEC filings and market data.
- **Use primary sources.** We use SEC XBRL and proxy filings, and check that each XBRL number appears in the human-readable filing.
- **Use independent cross-checks.** We recompute TSR from prices and compare it with what companies report.
- **Use reconciliation rules.** Parsed pay components must add up to the reported total.
- **Run statistical sanity checks.** Robustness specifications, placebo (permutation) tests, and bootstrap confidence intervals.
- **Verify claims.** Every fact quoted in a case study must be found in the cited filing.
- **Look at everything.** We review every chart and every sentence against the data.

## Challenges and uncertainties we expect

- **Messy filings.** Proxy tables vary wildly between companies. Parsing may fail for some.
- **CEO changes.** Years with two CEOs need a clear rule.
- **Short history.** The SEC's pay-versus-performance disclosure only began in 2023 (up to 5 fiscal years).
- **Interpretation.** "Compensation actually paid" is partly linked to the stock price by construction.
- **Survivorship bias.** We sample today's index members.
- **Strategy test horizon.** Only one to two years of forward returns are available.
