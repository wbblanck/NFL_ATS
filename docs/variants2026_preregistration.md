# Pick-Model Variants on the 2026 Season: Pre-registration

Committed before any variant's result was computed. Research only: nothing here changes the official pick, the
live record, `data/predictions`, or any workflow. Plan approved by the user on 2026-10-23.

## Already seen (disclosed)

- The season records of the official pick, key-number shadow, v1, v3 and hybrid (dashboard, `live_record.md`).
- The week 1-2 per-game picks of those five (`data/backtests/early2026.json`) and the 16 rebuilt missed games
  (`docs/missed_picks_report.md`, the all-models table in the project files).
- The hybrid, edge2, key-number, patterns and mining reports. The 2014-2024 seasons have been reused by several
  studies, so the history checks below are sanity checks, not clean holdouts.
- No outcome of any candidate below, in any season.

## Data

**2026 (primary).** Every graded 2026 regular-season game, weeks 1-7, with a half-point pool line in
`data/lines/league_lines.csv`, as of the run. Three buckets, always also reported apart:

| Bucket | Games | Market | Official pick used here |
|---|---|---|---|
| `early` | weeks 1-2 | nflverse closing spread (no captures yet) | re-run at lock, as in `early2026.py` |
| `live` | recorded picks with a market | recorded `market_at_lock` | recorded pick and cover probability |
| `rebuilt` | 7 never-picked + 9 no-market fallback games | OddsPapi Pinnacle, kickoff − 20 min | the reconstruction in `data/hypothetical/missed_picks_2026-10-20.csv` |

The 9 recorded fallback picks (always away) stay in the official record; here they are replaced by their
reconstruction so every model is judged on a real market. Total: recorded `market_total`, else the schedule total.

**History (sanity check only, cannot promote a candidate on its own).**
- `sbro`: SBRO half-point opens as the proxy pool line, nflverse close as the market, 2007-2021. 2007-2013 is
  used only to fit the blend weight; 2014-2021 is the check.
- `cbs2025`: 2025 CBS-open games in `data/backtests/players2025_games.csv` (open = pool line proxy, close =
  market, recorded v1 cover probability).
- The AusSportsBetting price file is not on this machine, so the price candidate has no history check.
- v3 has no history on these line sets, so v3 candidates have no history check.

## Notation

Pool line L (home spread), market m, total T. `p_off(m)` = the official estimator's P(home covers L) given
market m: the total-conditioned shifted distribution fitted on games before the lock (`final.fit_total_dist`).
Every candidate picks home when its probability is above 0.5. v1 and v3 probabilities are the ones recorded at
lock in `projections.csv`; where no row was recorded they are recomputed with the live code and current data
(flagged `recomputed`; v3 recomputations are approximate because injury data is as of today). Projection spread
P = −(projected home points − projected away points).

## Candidates (13 tests)

**10 is void.** "Total-conditioned spread" is already how the official estimator works (`TotalDist`,
`total-shifted-empirical-argmax`), so it is not a variant. Found from the code before any result; dropped, not
replaced.

**A. Market input** (need the lock-time multi-book capture: `live` bucket only; elsewhere they equal official).
The lock snapshot is each book's latest row for the game in `market_captures.csv` captured between 10 minutes
before and 2 minutes after the pick's `created_at`.

1. **C1 fresh.** Keep only books whose `book_last_update` is within 10 minutes of the capture. Market =
   Pinnacle if fresh, else the median of fresh books if 3 or more, else the official market. Pick = `p_off`.
2. **C2 price.** For the same books the official used (Pinnacle, else all books), the no-vig home cover
   chance q = (1/price)/(1+h), with h = 0.027 for Pinnacle and 0.045 for other books (away prices are not
   captured, so the hold is assumed). Each book's line is replaced by the spread m' at which the official
   distribution gives P(home covers that book's line) = q (grid of 0.05 points within ±3 of the line). Market =
   Pinnacle's m', else the median m'. Pick = `p_off`.
3. **C3 momentum.** Trend = m − (median of books at the last capture at least 18 hours before lock). Predicted
   close = m + k × trend, with k from a least-squares fit of (nflverse close − m) on trend over earlier weeks'
   `live` games only (no outcomes used; k = 0 with fewer than 10 earlier games; k clipped to [0, 1]).
   Pick = `p_off` at the predicted close.
4. **C4 agreement gate.** The hybrid, but a 1+ point move also counts as "no move" when fewer than 60% of the
   lock-snapshot books sit strictly on the same side of L as m. Off the `live` bucket it equals the hybrid.

**B. Blends.**
5. **C5a/C5b/C5c blend.** Market = m + w × (P − m), pick = `p_off` at that market, for P from v1 (a), v3 (b),
   and the mean of v1 and v3 (c). w is the least-squares slope of (margin + m) on (m − P_v1) over `sbro`
   2007-2013 with v1 refit before each week (live constants), clipped to [0, 1]. The same w is used for v3 and
   the mean (no v3 history). Where P is missing, the official pick.
6. **C6a/C6b/C6c hybrid fill.** |drift| ≥ 1: official pick. Otherwise: v3 (a), mean of v1 and v3 cover
   probabilities (b), key-number shadow (c). Missing fill: official.
7. **C7 double disagree.** Official, except switch when v1 and v3 both pick the other side.
8. **C8 vote.** Majority of official, key-number, v1, v3, hybrid (missing votes left out; ties: official).

**C. Key numbers.**
9. **C9 key straddle.** The key-number shadow's pick when a key number (3, 6, 7 or 10, either sign) lies between
   L and m (inclusive of m); else official.

## Primary test (decides)

For each of the 13, on the pooled 2026 games: the games where it picks differently from the official pick;
wins of the candidate vs wins of the official on those games; one-sided exact binomial p (candidate better).
**Holm correction across the 13 at family-wise 5%.**

## Secondary (reported, do not decide)

- Record against the pool line, overall and per bucket, next to official, key-number, v1, v3 and hybrid; and net
  vs the hybrid for C4 and C6.
- Mean cover margin of the pick (points by which the picked side beat the pool line), candidate minus official,
  with a 95% interval from resampling whole weeks (4,000 draws).
- Brier score of P(home covers L) for candidates with a probability (C1, C2, C3, C5).
- Null band: the 95% range of wins from coin-flip picks on the same number of games.
- History: net vs official on `sbro` 2014-2021 and `cbs2025` for C5a, C6c, C9 (the only ones the data allows).

## What a result means

- **Track live** (shadow, like the hybrid) only if Holm passes, or if the unadjusted p ≤ 0.10 and the net is
  ≥ 0 on every available history set. Otherwise: no evidence.
- Nothing changes the official pick without the user's approval and the 256-game rule.

## Power, stated in advance

About 90 graded games. A candidate that differs on 10 games needs 10 of 10 to pass Holm's first step
(0.05/13 = 0.0038; 9 of 10 gives p = 0.011). A pass is very unlikely even for a real improvement; the most likely
outcome is "no evidence", which is not evidence of no effect.
