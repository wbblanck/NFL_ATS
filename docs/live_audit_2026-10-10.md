# Live pick audit, 2026-10-10

Read-only checks on the live pick path, the dashboard record, and the alerts. No live pick, record, or model was changed.

## Checked

- **Tests:** 194 passed before the retry change.
- **Lock times:** match the scheduled lock routines for PHI @ JAX (13:15 UTC), BAL @ ATL (00:05 UTC), and BUF @ LA (00:00 UTC). Daylight saving is handled.
- **Spread sign:** the convention (negative = home favored) holds for the pool lines against Pinnacle captures (46 of 46 agree), SBRO closes against nflverse (3,916 of 3,933), and CBS 2025 opens against nflverse closes (256 of 271; the flips fit the normal open-to-close movement).
- **Picks:** all 31 rows for 2026 have a side that matches their probability and a team that matches the side.
- **Record:** recomputed from picks and results against the pool lines: 17-14. The dashboard shows 17-14.
- **Alerts:** the spread printed for each pick matches the pool line for all 31 picks.

## Unlabeled picks

Seventeen picks from weeks 3 and 4 have `feature_version` set to `none`, though they carry market values. In all 17 cases, `market_at_lock` equals the median of every book in the capture taken at pick time. None used Pinnacle. That matches the median policy in force before the October 4 switch, so these picks should read `market:median` (pre-switch). This note is the record of that. `predictions.csv` is not edited.

## Finding: one pick on a single missing Pinnacle line

TB @ DAL (October 8) fell back to the median of a few books (`MARKET_MEDIAN_FALLBACK`, `FEW_BOOKS`). It's the only 2026 pick on the fallback. The proposed change is one retry 60 seconds after the first capture, when Pinnacle is missing. It's committed to the research branch with tests and is not merged.

## Not checked

- Research modules, beyond the spread-sign convention.
- The stale-line policy. That's a decision for after the season.
