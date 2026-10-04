# Market Input: Pinnacle (from 2026-10-04)

From week 4's Sunday games on, the market line the pick is made from is **Pinnacle's spread at lock**.
Before that it was the median of every book's spread (13–15 books).

- **Decision:** the user's, 2026-10-04. It was not a pre-registered test result.
- **Evidence it rests on:**
  - **Our earlier test** (`docs/sharp_line_report.md`, 2014–2017, 379 games): using Pinnacle's close instead of the consensus changed 3 picks, which went 2–1. Log loss was 0.6900 vs 0.6904. That is no measurable difference either way.
  - **Our 2026 captures, weeks 3–4:** when Pinnacle disagreed with the other books early, the line later moved its way in 3 of 4 games. That is too few to distinguish from chance (one-sided p = 0.31).
- **Fallback:** when Pinnacle has no line at lock, the pick uses the all-book median and is flagged
  `MARKET_MEDIAN_FALLBACK`. The phone's CHECK PICKS alert names the game. Near lock, Pinnacle was present in 19 of 21 captured game snapshots in weeks 3–4.
- **Recorded per pick:** `feature_version` is `market:pinnacle` or `market:median`. `market_at_lock` is the line actually used. Every book's line is still captured in `data/lines/market_captures.csv`, so the season can be re-scored with either input.
- **Unchanged:** the margin model, the cover-probability rule, and the timing (pick 5 minutes before lock).
- **Already locked:** the week 4 picks for PIT@CLE and IND@WAS used the median. Both Pinnacle and the median were captured for them.
