# Hybrid Rule: Live Tracking Plan

Written 2026-09-30, before any 2026 hybrid result was computed. The rule failed its backtest
(docs/hybrid_report.md); the user asked to follow it live. It is a **tracked comparison and never makes the pick**.

## Rule (frozen)

- Market moved 1+ point off the pool line at lock (|drift| ≥ 1): the live pick.
- Moved ½ point or not at all: the proj-poisson-v1 pick against the pool line, as recorded at lock in
  `projections.csv`. If that pick is missing, the live pick.

Both inputs are written at lock (`predictions.csv` drift and pick, `projections.csv` v1 pick), so the hybrid uses
nothing after the lock. Code: `engine/picks/hybrid.py`; graded in `engine/picks/live.py`; shown on the dashboard.
It starts with the 2026 week-3 picks (the first with both rows recorded).

## How it is judged

- Only the games where the hybrid and the live pick differ count: hybrid-right minus live-right (the "net").
- **Promising** only if z = net / √(games that differ) ≥ 1.645 (one-sided 5%), e.g. net ≥ +17 over 100 games
  that differ. About 30 games differ per season, so that needs roughly three seasons.
- Reviewed at the end of each season and each time 100 differing games are reached, never mid-way by
  cherry-picking a stretch. The record is shown every week.
- Switching the live pick would need that bar met and the user's approval.
