# Generation 2 game-level lineup test, 2021 (preregistered)

Run 2026-11-11 once, per `PREREGISTRATION_game_level.md` (committed before scoring). Script `scripts/gamesim_v2/game_level_test.py`, numbers in `data/gamesim_v2/manifests/game_level_2021.json`.
544 team-games of the 2021 regular season. Outcome and form built from earlier plays only; lineups from the pregame snapshot with player effects estimated before each game's week. 2022-2025 not loaded. No lines, no picks.

## Headline

**The pregame lineup shift has the right sign on all three outcomes but is not distinguishable from zero, so the preregistered pass rule fails: no evidence in one season.**
Team form (the aggregate baseline) carries the signal: its coefficient on EPA per dropback is 0.81 for the offense and 0.49 for the opposing defense.

## Results

| Outcome (per team-game) | Lineup predictor | Coefficient (95% interval) | Effect of one standard deviation | Leave-one-week-out error change, form + lineup minus form only (95% interval) |
|---|---|---|---|---|
| EPA per dropback (primary) | S (completion shift plus negated pressure shift) | +0.0175 (-0.0040 to +0.0388) | +0.026 EPA per dropback | -0.00013 (-0.00114 to +0.00094) |
| Pressure-or-sack rate | -P (negated pressure shift) | -0.017 (-0.082 to +0.051) | -0.003 | +0.00003 (-0.00001 to +0.00007) |
| Completion rate | C (completion shift) | +0.065 (-0.013 to +0.150) | +0.009 | -0.00001 (-0.00009 to +0.00007) |

Pass rule G1 (EPA coefficient interval above zero and the error change interval below zero): **both fail**. Weighted outcome standard deviations: EPA 0.32, pressure rate 0.097, completion rate 0.094.
Expected signs were positive for S and C and negative for -P; all three came out the expected way.

## Reading it

- One standard deviation of lineup shift is worth 0.026 EPA per dropback at the point estimate, about 0.9 points per team-game at roughly 36 dropbacks. The interval runs from slightly negative to about two points. The test cannot tell these apart; this is the power problem stated in advance.
- Adding the lineup shift lowers out-of-sample error by 0.13% for EPA and a hair for completion, and raises it slightly for pressure. None is distinguishable from zero.
- The pressure and completion shifts are nearly uncorrelated with each other (r -0.07), so S mixes two separate signals.
- This matches the play-level result: tiny, correctly signed, and not clearly more than team form.

## Decision (per the preregistration)

Fail: no detectable pregame lineup effect at the game level on 2021. Recommendation: do **not** build the full drive and game engine on these inputs. If Will wants to keep testing, the cheaper options are (a) add 2020 and 2019 team-games to the same test as a development read only (the 2021 test is spent), or (b) wait for a fresh season of forward data. Neither touches the locked 2022-2025 seasons.
Limits: one season, 544 team-games, effects set to 0 for unseen players, expected lineups limited by the snapshot's injury and workload data, outcomes limited to passing offense.
