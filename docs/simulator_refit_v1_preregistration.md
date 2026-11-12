# Simulator refit, stage 1: V0r (refit on newer data) and V1 (opponent adjustment). Pre-registration

Research only; nothing here touches the live pick pipeline. Branch `claude/project-thread-bxmkrr`. Written and committed
before either candidate has been run on any season. Plan and acceptance criteria: `docs/simulator_refit_plan.md`.

## Candidates (each compared with V0, one change at a time)
- **V0** (control): constants and league tables frozen on 2016-2020 (`data/gamesim/gamesim_constants.json`,
  `gamesim_league.json`), team factors from `teams.factors`, QB and injury layer as ported.
- **V0r** (answers "use the data that's available now"): for each test season t, the play-level league tables
  (`league.fit` + two-point decision + clock) and the league rates used by the team factors are refit on 2016..t-1.
  Tuned constants stay frozen (h 8, k 8, r 0.7, hfa, personnel coefficients). Rebuilding the tables from 2016-2020
  reproduces the stored `gamesim_league.json` exactly (checked 2026-11-12), so for 2021 V0r equals V0 and only
  2022-2025 differ.
- **V1**: V0 with opponent-adjusted team factors (`src/engine/gamesim/teams_adj.py`). Each factor is shifted by the
  data-share-weighted average of the opponents' pre-game opposite-side factors (formula in the module docstring); no
  other change.
  Sanity check before any scoring (2015-2017 factors only, no outcomes): V1 factors correlate 0.98-0.99 with V0's and
  differ by about a tenth of a factor's spread, because the season prior (k = 8 games) dominates. Expect a small effect.

## Harness
`scripts/sim_refit_harness.py <cache> <version>`: seasons 2021-2025, regular season weeks 2-18, seed 101, 1000 runs per
game, fit only on seasons before the test season. Totals are now saved (`run.simulate_games(..., return_totals=True)`).
Scoring: `scripts/sim_refit_score.py`. Outputs are git-ignored parquet plus `data/gamesim/refit/score_v1.json`.

## Primary metrics (paired by game, candidate minus V0; negative = better)
1. Margin MAE (sim fair margin vs actual margin).
2. Margin-distribution log loss (121 integer cells, smoothing alpha 0.1 on 1000 runs, as `scripts/sim_baseline_v0.py`).
Intervals: 95% paired bootstrap over games (10,000 resamples, seed 7), pooled over the candidate's seasons.

## Pass rule (per candidate, Holm over the two candidates at 0.05 on the one-sided paired test of metric 1)
A candidate passes only if all hold:
- pooled margin MAE and pooled log loss both lower than V0, each with a 95% interval excluding zero;
- MAE lower than V0 in at least 3 of 4 seasons (V0r, 2022-2025) or 4 of 5 seasons (V1, 2021-2025);
- no secondary metric worse by more than: total MAE +0.1, ATS Brier vs close +0.005, moneyline Brier +0.005.
These seasons are development data (2022-2025 were already used to confirm V0), so a pass makes the candidate eligible
for frozen forward predictions, not for adoption. A fail means no evidence of improvement.

## Secondary metrics (reported, not tested)
Total MAE vs actual and vs the closing total; ATS Brier of the cover probability vs the close; ATS record of the
simulator's side vs the close; moneyline Brier vs actual winner next to the no-vig closing moneyline; key-margin
frequencies (1, 2, 3, 4, 6, 7, 8, 10, 14), with 3-point frequency split by closing-spread size, closing-total size and
actual overtime; per-season tables.

## Power (stated in advance)
Season-to-season V0 margin MAE moves by more than 1 point, but paired game differences between close variants are
small. With about 1,000-1,280 games, a paired interval can resolve MAE gains of roughly 0.05-0.1 points only if the
versions' errors are highly correlated (they will be). Any ATS effect is far below what these samples can detect.
