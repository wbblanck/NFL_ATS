# Teasers Through 3 and 7: Pre-registration

Committed before any teaser leg was graded. Code: `engine/backtest/alt_markets.py` (`run_teasers`), known-answer
checks in `tests/test_alt_markets.py`. Output: `data/backtests/alt_markets.json` → `docs/alt_markets_report.md`.

Question: do 6-point teaser legs that move a closing spread through both 3 and 7 win often enough to beat a
2-team teaser's price? This is a real-money question; it does not touch the pool pick.

## Seen before this was written (disclosed)

Line-only counts, no results: Wong-window sides per season in the committed close files, and (this file's data)
589 half-point legs in 2015–2025 (387 dog, 202 favorite) and 478 in 1999–2014, median closing total 45.0 and 42.0.
No leg outcome has been computed.

## Data

- nflverse schedules: closing spread (`spread_line`, source book unverified), closing total, final score.
  Regular season, 1999–2025.
- **Leg:** a side whose closing spread is +1.5, +2 or +2.5 (teased to +7.5..+8.5) or −7.5, −8 or −8.5 (teased
  to −1.5..−2.5). A game has at most one leg. Overtime counts (as books grade it).
- Primary legs are half-point closes (no push possible). Whole-number legs are reported only.

## Tests (family of 2, Bonferroni: one-sided 2.5% each)

Era for the decision: **2015–2025** (current extra-point distance; key-number frequencies may differ before).

- **H1** all half-point legs.
- **H2** half-point legs whose closing total is at or below that era's median (45.0, computed from lines only).

Statistic: leg win rate, 95% interval from a week-clustered bootstrap (4,000 resamples).
**PASS** if the interval's lower end exceeds the 2-team −120 per-leg break-even, √(120/220) = 73.85%.
Also reported: whether it clears the −110 break-even (72.37%), 1999–2014 for comparison, dog vs favorite legs.

## Limits

Close is not the price at bet time; teaser prices vary by book (some offer −110, many −120 or worse); legs in the
same week are treated as independent for the break-even (the bootstrap keeps weeks together).
