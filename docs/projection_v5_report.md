# Projection v5: Report (validation failed, not scored)

The rules are in `docs/projection_v5_preregistration.md` (commit `5f76c2e`). The output of the final run is in
`data/backtests/projection_v5_validation.json`. By rule, **no 2022–2025 result was computed**.

## Implementation notes and a bug found during validation

1. **Drive duration is measured start-to-start:** from a drive's first snap to the next drive's first snap. The
   pre-registration said "duration in game-clock seconds". First-to-last snap misses about 7 s a drive; the
   start-to-start measure sums to 1,800 s per half. This was set before any validation check ran.
2. **Overtime follows the actual 2017+ regular-season rules:**
   - a first-possession TD wins;
   - after a first-possession FG, the opponent gets one possession;
   - then the next score wins.

   The pre-registration's shorthand ("ends at a TD or a FG not on the first possession") did not describe the
   guaranteed possession correctly.
3. **Bug: defensive-TD drives were counted twice.**
   - The first validation run failed with simulated points **24.84 vs 23.03** per team.
   - Diagnostics on training data showed the cause. Drives had been grouped by (game, drive, **possession
     team**). The extra point after a return TD has the scoring team as `posteam`, so every defensive-TD drive
     was split into a real drive and a phantom "drive" by the scoring team, also ending in "opponent TD".
     That doubled the defensive-TD rate (2.6% of drives instead of 1.3%) and added phantom drives.
   - Drives are now keyed by (game, drive). The play-by-play reconciles: 5.13 offensive + 0.26 defensive TDs =
     5.39 total per game.
   - The validation was re-run. Nothing about the model changed, and no test data was touched.

## Validation (after the fix)

| Check | Result | Required | Verdict |
|---|---|---|---|
| TD reconciliation / neutral / point-in-time | 99.87% / 0 / identical | — | Pass |
| Drive model: TD odds vs expected TDs | γ = 1.07 | reported | — |
| Late game, TD share trailing 9+ vs leading 9+ | data 28.6% vs 16.7%; model 30.4% vs 15.7% | trailing > leading | Pass |
| Points per team | simulated 23.60 vs 23.03 | ±0.3 | **Fail** |
| TD / FG dispersion | 0.775 / 0.990 vs 0.774 / 0.981 | ±0.05 | Pass |
| Max residual-correlation gap | 0.105 (home TD vs away TD: 0.053 vs 0.158) | ≤ 0.05 | **Fail** |
| 50% coverage (training) | 0.538 | 0.47–0.53 | **Fail** |
| PIT deciles | 0.081–0.116 | 0.08–0.12 | Pass |
| Margins of exactly 3 / 7 | 10.5% / 6.2% vs 14.2% / 8.7% | ±1.5 pp | **Fail** |
| Internal holdout (2019–21) | coverage 0.514 | 0.46–0.54 | Pass |

The first, buggy run had these values:

| Check | Buggy run |
|---|---|
| Points per team | 24.84 |
| Max correlation gap | 0.074 |
| Coverage | 0.499 |
| Margins of 3 / 7 | 11.4% / 6.5% |

Part of its apparently better cross-team correlation came from the phantom drives.

## What this shows

- **Scoring variability is now right.** Simulating drives with game-state effects reproduces how much TD and FG
  counts vary, which v3, v4 and v4.1 could not.
- **Two things are still missing:**
  1. The link between the two teams' scores: 0.05 simulated vs 0.16 real.
  2. Key-number margins: games decided by exactly 3 and 7 are under-produced by 2.5–3.7 points.
- **The likely reason is coarse late-game states.** "Trailing by 1–8" merges a team down 3, which needs a FG,
  with a team down 8, which needs a TD and a 2-point conversion. End-of-game decisions around one-score margins
  are what create 3- and 7-point finishes and the two teams' scoring responses.

## Status

v5 is **not adopted**. v3 stays the tracked projection.
