# Second-Half (Halftime) Lines: Pre-registration

Committed before any second-half bet was graded. Code: `engine/backtest/alt_markets.py` (`run_halftime`,
`parse_page_full`), checks in `tests/test_alt_markets.py` (parser on the 2015 PIT@NE row; a planted
over-reaction is found and an unbiased line is not). Output: `data/backtests/alt_markets.json`.

Question: does the second-half line, set in the minutes of halftime, misprice the first-half score?

## Seen before this was written (disclosed)

Parse coverage only: all 15 SBRO season files (2007–2021) have a numeric 2H and ML cell on every row; 4,008 of
4,025 matched games parse to a 2H spread and total (4 ambiguous, 13 out of range). One game's raw row was read to
check the parser. No second-half result has been graded.

## Data

- SBRO season pages (`data/raw/sbro/`): quarter scores, final score, second-half spread and total (one row holds
  the 2H favorite's spread, the other the 2H total; the larger number is the total). Source book and posting time
  UNVERIFIED; no prices, so −110 is assumed (break-even 52.38%).
- Regular season only (joined to nflverse REG games). Second half includes overtime (final minus first half).
  Pushes on the 2H line are dropped. Pregame expectation: nflverse closing spread.
- **Fit seasons 2007–2014; test seasons 2015–2021.**

## Tests (family of 2, Bonferroni: one-sided 2.5% each), graded on 2015–2021

- **H1** back the team trailing at halftime against the 2H line (tied halftimes skipped).
- **H2** OLS on 2007–2014: 2H home margin = a + b·(2H line's expected home margin) + c·(pregame expected home
  margin) + d·(first-half home margin). On 2015–2021, bet the side the prediction favors over the 2H line.

**PASS** if the week-clustered 95% interval of the win rate has its lower end above 52.38%. The fitted
coefficients are reported (d < 0 together with b near 1 would mean the line over-reacts to the first half).
