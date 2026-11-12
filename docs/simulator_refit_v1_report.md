# Simulator refit, stage 1 report: V0r and V1 both FAIL

Pre-registration: `docs/simulator_refit_v1_preregistration.md` (commit 98ad867, before any run). Run once, 2026-11-12.
Harness `scripts/sim_refit_harness.py`, scorer `scripts/sim_refit_score.py`, numbers in `data/gamesim/refit/score_v1.json`.
Regular season weeks 2-18, seed 101, 1,000 runs per game, each season fit only on earlier seasons.
These seasons are development data (2022-2025 already confirmed V0), so this is a screen, not evidence for adoption.

## Headline
Neither change improves the simulator. Refitting the play tables on newer data (V0r) and adjusting team factors for
opponents (V1) both move margin error by a few hundredths of a point in either direction, well inside noise.

| | V0r (refit 2016..t-1), 2022-2025 | V1 (opponent-adjusted), 2021-2025 |
|---|---|---|
| Games | 1,023 | 1,279 |
| Margin MAE, candidate minus V0 (95% interval) | -0.003 (-0.041 to +0.036) | +0.021 (-0.025 to +0.067) |
| Margin log loss, candidate minus V0 | +0.011 (-0.018 to +0.039), worse | +0.012 (-0.017 to +0.040), worse |
| Seasons with lower MAE | 3 of 4 (needed 3) | 2 of 5 (needed 4) |
| One-sided p (MAE), Holm | 0.45, not significant | 0.82, not significant |
| Result | **FAIL** | **FAIL** |

MAE difference by season, V0r: 2022 -0.009, 2023 -0.044, 2024 -0.020, 2025 +0.061.
V1: 2021 -0.007, 2022 +0.034, 2023 +0.035, 2024 -0.023, 2025 +0.068.

Why V1 does so little: with the season prior worth 8 games, the opponent correction is about a tenth of a factor's spread
(V1 and V0 factors correlate 0.98-0.99), so it barely changes the simulated games.

## Secondary metrics (pooled; V0 / candidate)
2022-2025 (V0r comparison, 1,023 games):
- Margin MAE: V0 9.991, V0r 9.989; closing spread 9.537.
- Total MAE: V0 10.39, V0r 10.35; closing total 10.16. The simulator's totals are worse than the market's.
- ATS Brier of the cover probability vs the close: V0 0.2611, V0r 0.2612 (always 50% = 0.250).
- ATS record picking the simulator's side vs the closing spread (pushes excluded): V0 495-499, V0r 489-505.
- Moneyline Brier vs the actual winner (ties excluded): V0 0.2262, V0r 0.2257; no-vig closing moneyline 0.2099.

2021-2025 (V1 comparison, 1,279 games): margin MAE V0 10.232, V1 10.254; total MAE 10.53 / 10.49 (close 10.31);
ATS record vs close V0 607-639, V1 601-645; moneyline Brier 0.2265 / 0.2266 (market 0.2108).

## 3-point margins (diagnostic, V0, 2022-2025)
The 3-point shortfall (11.5% simulated vs 15.2% actual) sits in close games, not lopsided ones:

| Games | n | Actual 3-pt share | Simulated |
|---|---|---|---|
| Closing spread 0-2.5 | 257 | 15.6% | 12.2% |
| Closing spread 3-6.5 | 497 | 17.5% | 11.9% |
| Closing spread 7+ | 269 | 10.4% | 10.4% |
| Games that went to overtime | 59 | 57.6% | 11.7% |
| Games decided in regulation | 964 | 12.6% | 11.6% |

Guess at the time (checked below, about half right): much of the shortfall looks like overtime. Real overtime games end by 3 about 58% of the time,
and the 59 overtime games alone account for about 2.7 of the 3.7 percentage-point gap. This comparison is unfair to the simulator
(it conditions on real overtime, not the simulator's own), so the next check is the simulator's own overtime rate and
how its overtime games end. Neither refit moved any key-margin frequency by more than 0.2 points.

## Other findings this stage
- Bug fixed: the ported `scripts/gamesim_reproduce.py` attached each game's margin distribution to the wrong game. Fixed;
  Sprint 1 baseline distribution figures corrected in `docs/simulator_refit_plan.md`. sim_fair and elo_fair were always
  right, so batch 2 and the hybrid-with-simulator result stand.
- Weather source: nflverse schedules carry game temperature and wind for 93% of outdoor games 2016-2025 (98% in 2025);
  domes and closed roofs have none, as expected. Whether these are pregame forecasts or observed values is not verified.
- Rebuilding the league tables from 2016-2020 play-by-play reproduces the stored tables exactly, so refits are now
  reproducible from code.

## What this means for the plan
The two cheapest broad changes did nothing. Margin MAE is set by team strength inputs that the market already prices
better (close 9.54 vs simulator 9.99), and the play-level tables are stable across 2016-2024. Of the remaining stages,
the one with a concrete measured defect is the endgame/overtime engine (V5): the 3-point and 7-point frequencies are off
in a structured way. That could improve the shape of the distribution (useful for teaser, total and key-number questions)
without any promise of a better side against the spread.

## Addendum 2026-11-12: overtime check (V0, 2022-2025, 1,023 games, descriptive)
`scripts/sim_ot_diag.py` -> `data/gamesim/refit/ot_diag.json`, using the simulator's own end-of-regulation score.

| | Actual | Simulator |
|---|---|---|
| Games reaching overtime | 5.8% | 4.5% |
| Overtime games ending by exactly 3 | 57.6% (of 59) | 34.0% |
| Overtime games ending by 6 or more | 33.9% | 53.1% |
| Overtime ties | 3.4% | 6.7% |

Share of all games, split by how they were decided (actual vs simulator):
- 3-point margins: regulation 11.8% vs 9.9%, overtime 3.3% vs 1.5%. The 3.7-point gap is about half regulation, half overtime.
- 6-point margins: overtime 1.9% vs 0.1%. 7-point margins: overtime 0.1% vs 2.2%. In regulation both match (6: 4.8 vs 4.7; 7: 8.0 vs 8.0).

**Engine bug found:** after a touchdown in overtime the engine scores the extra point or two-point try before checking
whether the game is over (`engine.py`, touchdown block: try added, then `check_ot`). In the NFL a game-ending overtime
touchdown has no try, so those games end by 6, not 7. This alone explains the simulator's surplus of 7s and shortage of
6s. The 2025 both-possessions overtime rule (`both_poss = season >= 2025`) and the 10-minute overtime from 2017 are coded correctly.

Remaining gaps after that bug: too few games reach overtime, too few overtime games end on a field goal, and too few
regulation games end by 3 (with too many 4s and 10s). These point at late-game field-goal and clock decisions.
Candidate V5 (not yet pre-registered): (a) no try after a game-ending overtime touchdown (a rules fix, no fitting);
(b) any endgame decision changes, fitted on 2016-2020 only.
