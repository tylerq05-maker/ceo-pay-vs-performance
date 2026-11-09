# Defense guide: be able to explain every part

The rubric says *"Explaining that 'the AI did it' is not enough."* Every group member should be able to give the 60-second pitch, explain each component below, and answer the likely questions. Each answer says where the evidence is.

---

## 1. The 60-second pitch

> CEO pay is supposed to align managers with shareholders, and funds vote on it every year. We built an AI-assisted research system that pulls five years of CEO pay and shareholder returns for 100 S&P 500 companies straight from SEC filings. It rebuilds the returns independently from market prices and checks every number against its source.
>
> **Finding 1.** The pay boards *award* barely tracks returns: TSR explains 0.5% of it. Company size matters far more. The pay CEOs *realise* does track returns (46%), because it is mostly stock.
>
> **Finding 2.** The biggest outliers come from specific structures: mega-grants, retention awards, founder grants and grant timing. They are not boards rewarding failure.
>
> **Finding 3.** Shareholders vote against the *size* of pay, not weak returns. Excess pay did not predict future returns in 2024–26.
>
> **Validity.** We prove the numbers with nine automated checks and replicate the results on the full S&P 500. We caught 27 real errors along the way, including some in the companies' own filings.

---

## 2. Suggested split for presenting

| Section | Slides | Owner |
|---|---|---|
| Question, why it matters, what we built | 1–5 | [name] |
| Findings: pay vs. TSR, size, outliers, case studies | 6–9 | [name] |
| Say-on-pay and the strategy test | 10–11 | [name] |
| Validation, errors caught, demo | 12–14 | [name] |
| Course concepts, limits, takeaways, Q&A lead | 15–17 | [name] |

---

## 3. Every component, in plain English

| Component | What it does | The decision we made, and why | File |
|---|---|---|---|
| Universe | Lists today's S&P 500 and draws 100 companies in proportion to each GICS sector | Stratified so every sector is represented; `FULL_UNIVERSE=1` runs all 500 | `src/universe.py` |
| PvP XBRL parser | Reads the SEC pay-versus-performance facts from each latest proxy: CEO pay, compensation actually paid, company and peer TSR | Use the newest proxy (longest history). In a year with two CEOs, use the one in office at year-end | `src/pvp_xbrl.py` |
| SCT parser | Reads the Summary Compensation Table HTML for salary, bonus, stock, options and so on | Keep a row only if components sum to the total **and** the total equals the XBRL figure | `src/sct_parser.py` |
| Market data | Downloads prices and dividends; builds a total-return index | TSR = price change + reinvested dividends, over the same fiscal years as the pay | `src/market_data.py` |
| Analysis | Regressions, outliers, pay mix, panel, say-on-pay | Log pay (pay is skewed), start-of-window size, sector controls, robust errors, winsorized TSR | `src/analysis.py` |
| Strategy test | Sorts companies by "excess pay" and measures later abnormal returns | Point-in-time formation dates; CAPM abnormal returns; medians and rank tests because single stocks dominate means | `src/strategy.py` |
| Backtest | Daily long-short portfolio, re-formed each September; Sharpe, drawdown, CAPM alpha and beta | Newey-West t-stats; equal weights; no transaction costs (they would only hurt) | `src/backtest.py` |
| Replication | Re-runs everything on all S&P 500 companies and compares | Separate output folders; SEC share counts for size | `src/replication.py` |
| Validation | Nine automated checks | Each targets a different way the output could be wrong | `src/validate.py` |
| Screener and AI analyst | Interactive tool; Claude explains a company and every number in its answer is checked against the data | The AI sees only the verified record; unmatched numbers turn red | `src/screener.py` |
| Report | 5-page write-up rendered from `results.json` | No number typed by hand | `src/report.py` |

---

## 4. Questions we expect, with answers

**Q: What is the difference between "granted pay" and "realised pay"?**
Granted pay is the Summary Compensation Table total: salary, bonus and the *grant-date value* of stock and options, which is what the board decided to award. Realised pay is the SEC's "compensation actually paid" (CAP). It revalues the CEO's equity at year-end prices, so it moves with the stock. *Evidence:* `ASSUMPTIONS.md` C11, A2.

**Q: Isn't it circular that realised pay correlates with TSR?**
Partly, yes, and we say so on the slide. CAP marks equity to market, so a rising stock raises CAP almost mechanically. The informative result is the *contrast*: what boards award barely moves with returns, so alignment comes from the stock CEOs already hold, not from boards adjusting pay.

**Q: Why log pay? Why asinh for CAP?**
Pay is very right-skewed ($1.7M to $79M), so logs make a 10% difference mean the same thing at any level. CAP can be negative (40 CEO-years are), and logs can't take negatives. asinh behaves like a log for large values but works for negatives.

**Q: An R² of 0.5% is tiny. Isn't low R² normal in finance?**
Low R² alone isn't the point. The TSR *coefficient* is small and statistically indistinguishable from zero: +1.8% pay per 10 points of TSR, p = 0.69, with a bootstrap 95% CI of −4% to +12%. The permutation test confirms it: shuffled TSR fits as well as real TSR (p = 0.52). By contrast, size alone adds about 10 points of R².

**Q: Why control for size, and why size at the *start* of the window?**
Bigger companies pay more, a well-known result. If we used *current* market cap, companies whose stock rose would look bigger, and size would soak up part of the TSR effect. Measuring size before the window avoids that. A robustness check with current market cap and with revenue gives the same answer.

**Q: Why winsorize TSR? Isn't that manipulating the data?**
Palantir returned about 203% a year. One point like that can tilt a line. Winsorizing caps the top and bottom 2.5%. We also report the *raw* result (−1.8% per 10 points, p = 0.74) and rank-based results, so nothing hinges on it. *Evidence:* report robustness table.

**Q: What is a residual, and why does it identify outliers?**
The model predicts each company's pay from its TSR, size and sector. The residual is actual minus predicted (in logs), so +244% means Ares paid 3.44 times what the model predicts.

**Q: Your "overpaid" companies all had great returns. How are they overpaid relative to performance?**
Because TSR barely affects predicted pay, the model gives a high-return company almost the same prediction as a low-return one. So the residual mostly measures pay relative to size and sector. That is itself a finding, and we say so. For the intuitive case of high pay with weak returns, we added a misalignment screen; Omnicom tops it, and its cause is a front-loaded option grant.

**Q: How did you handle CEO changes?**
The XBRL tags each CEO separately. We take the CEO in office at fiscal year-end, flag the year, and keep the alternative "CEO-seat" total (all CEOs summed). Results are the same either way (robustness table). *Evidence:* `ASSUMPTIONS.md` C4–C5; the unit test `test_pvp_multi_ceo_incumbent_and_cumulative_tsr`.

**Q: How do you know the SEC XBRL numbers are right?**
For all 100 companies, the XBRL CEO pay figure appears verbatim in the human-readable proxy (100/100). The pay mix we parsed separately reconciles to the same totals (301/301 rows).

**Q: You say companies' own TSR figures are wrong. How do you know it's not your mistake?**
Three things. Our TSR matches Yahoo's adjusted prices to 0.02%. It matches the proxies to a median 0.07 points. For the 12 companies that disagree, the gap has a mechanical explanation: their earlier years match our TSR measured from the *previous* table's base date ("stale base"), or BlackRock's match the *next* year ("misdated"). The latest-year figure agrees in 10 of the 12.

**Q: Could the AI have invented the case-study facts?**
That is exactly what `src/validate.py` checks. Each of the 27 filing facts in the case studies is regex-matched in the cited SEC document; 27 of 27 are found. News claims we could not verify in a filing are labeled as news.

**Q: How does the screener's AI fact-check work, and what are its limits?**
Claude receives only the company's verified record and is told to copy numbers exactly. The page extracts every number from the answer and matches it against the record. Matched numbers turn green; anything else turns red with a warning. Limit: it checks *numbers*, not *reasoning*. A wrong interpretation with correct numbers would pass, which is why we also show the underlying data beside it.

**Q: What is the strategy test, and why didn't it find anything when Cooper, Gulen & Rau did?**
- **Design.** We sorted companies into fifths by "excess pay", using only data public at the formation date (Sept 2024 and Sept 2025). We then measured CAPM abnormal returns: (return − T-bill) − β × (S&P 500 return − T-bill), with β estimated before formation.
- **Result.** The rank correlation was +0.03 in both cohorts (p ≈ 0.8).
- **Why it may differ from their paper.** Their sample was 1994–2011 and much larger. Ours has about 100 firms and one to two years of returns. Recent markets were also dominated by a few huge winners. So "no evidence of a signal yet" is the right reading, not proof there is none.

**Q: Why were the raw averages so different?**
Bloom Energy rose about 1,800% and sat in the "most overpaid" fifth. One stock out of 19 moved that group's average by about 90 points. We verified the move was real, as we did Moderna's +900% (August 2026 cancer-vaccine data), and switched to medians and rank tests.

**Q: Walk us through the backtest. What do Sharpe, alpha and beta tell you?**
- **Setup.** Each 30 September we re-form fifths on excess pay, then go long the most-underpaid fifth and short the most-overpaid fifth (equal-weighted, daily returns). That is the trade Cooper, Gulen & Rau's finding implies.
- **Raw result (sample).** The long-short lost 15.0% in total, a Sharpe ratio of −0.49.
- **Risk-adjusted result.** We regress the daily long-short return on the market's excess return (CAPM). Alpha is the return the market doesn't explain: −1.8% a year with t = −0.22, so indistinguishable from zero.
- **Beta explains the loss.** The long-short beta is −0.41, because the overpaid fifth has beta 1.25 and the underpaid fifth 0.85. Shorting high-beta stocks in a rising market loses money, so the loss is market exposure, not a pay effect.
- **Why Newey-West.** Its t-statistics allow for daily returns that are correlated over time.

*Evidence:* chart `08_backtest.png`, `results.json` → `backtest`.

**Q: Isn't 100 companies too small? Does it hold for the whole index?**
We re-ran the identical pipeline on every S&P 500 company (`FULL_UNIVERSE=1`) and compared the two side by side (report appendix, `09_replication.png`). The 100-company sample is the primary study because the case studies were researched on its outliers.

**Q: How did you measure size for the full index?**
Yahoo's quote service started refusing bulk requests during the full run. For the full index we therefore used SEC-reported shares outstanding × price, adjusted for later stock splits. We validated it on the 100 sample companies, where both exist: 97 of 100 agree with Yahoo within 10% (correlation 0.99). The three exceptions have explanations: Ares counts only its Class A units, and Kimberly-Clark and Skyworks have pending mergers.

**Q: How do you know your say-on-pay numbers are right?**
Two independent checks.
- **Hand checks.** We compared the parse against six 8-K filings by hand.
- **Automated cross-check.** We compared every vote we could against the support each company states about itself in its next proxy ("92.3% of votes cast"): 57 of 57 agree, with a median gap of 0.1 points.

That cross-check caught a real bug: Solventum's say-on-*frequency* vote had been read as a 99% say-on-pay result. The company says about 85%. We fixed the parser, added a unit test, and Solventum's vote is now excluded rather than wrong.

**Q: What about survivorship bias?**
We sample today's S&P 500, so companies that collapsed and left the index are missing. That biases returns upward. It probably biases the strategy test toward finding nothing, if failing firms overpaid. It's listed as the first limitation.

**Q: What did your group do versus the AI?**
- **We decided** the question, the data sources and every design rule (window, CEO rule, controls, winsorizing, outlier definition).
- **We reviewed** every output, and the 23-item error log in `AI_USAGE_AND_QC.md` is our review record.
- **The AI** wrote and ran the code.
- **Our rule:** AI is never the source of a number.

**Q: What would you do with more time?**
- Write case studies for the full-index outliers.
- Add firms that left the index.
- Spread mega-grants over their vesting period to measure "normal" pay.
- Use reported share counts for size.
- Extend the strategy test as more returns accrue.

---

## 5. Numbers to know cold

| | |
|---|---|
| Sample | 100 companies, 99 in the 3-year model, 496 CEO-years |
| TSR's share of granted-pay variation | 0.5% |
| Granted pay per +10 pts TSR (size + sector controls) | +1.8%, p = 0.69 |
| TSR's share of realised-pay variation | 46% |
| Realised pay per +10 pts TSR | about +58% |
| Rank correlation, pay with size vs with TSR | 0.55 vs 0.15 |
| Excluding 4 no-grant founders | +11.6% per 10 pts (p = 0.001); 2× size = +24% |
| Top above-model | Ares +244%, Palo Alto +222%, Booking +179% |
| Top below-model | Amazon −93%, Palantir −72%, Coinbase −57% |
| Say-on-pay vs excess pay | Spearman −0.30, p = 0.004; median support 92.2%; 247 meetings |
| Failed votes | 3M 45.0%, Palo Alto 46.1%, Skyworks 49.8% |
| Strategy rank IC | +0.03 in both cohorts |
| Backtest (sample) | Long-short −15.0%, Sharpe −0.49, CAPM alpha −1.8%/yr (t = −0.22), beta −0.41 |
| Validation | 100/100 source match, 301/301 reconcile, 27/27 claims, 57/57 votes vs self-reports, 15/15 tests |

## 6. Glossary

- **TSR (total shareholder return):** price change plus reinvested dividends.
- **SCT (Summary Compensation Table):** the proxy's standard pay table, at grant-date values.
- **CAP (compensation actually paid):** the SEC's realised-pay measure, with equity marked to market.
- **PvP (pay versus performance):** SEC rule Item 402(v), adopted 2022, first disclosed in 2023 proxies.
- **XBRL:** machine-readable tags inside SEC filings.
- **Say-on-pay:** shareholders' annual advisory vote on executive pay.
- **Residual:** actual minus predicted value from a regression.
- **HC3:** a way of computing standard errors that stays valid when errors are uneven across companies.
- **Winsorize:** cap extreme values at a percentile instead of deleting them.
- **Permutation test:** shuffle one variable many times to see how often chance alone produces a fit as strong as the real one.
- **Bootstrap:** resample companies with replacement to get a confidence interval without distribution assumptions.
- **CAPM abnormal return:** return beyond what the market and the stock's beta explain.
- **Rank IC:** the rank correlation between a signal and later returns.
- **Sharpe ratio:** average excess return divided by its volatility, annualized.
- **Maximum drawdown:** the largest peak-to-trough loss.
- **Newey-West t-statistic:** a t-statistic that allows for returns that are correlated over time.
- **Long-short (zero-investment) portfolio:** buy one group, short another of equal size; its return is the spread.
- **Survivorship bias:** studying only the firms that survived, which flatters returns.
