# Team-stat factors model, 10k simulations (`proj-factors-v7`): Pre-registration

Committed **before** any v7 feature was computed or any v7 result was seen.

## What the owner asked for (2026-11-02)

"Can we backtest running all these factors and doing 10k simulations". The owner pasted a team-stats glossary.
It defines nine season-to-date metrics, offense and defense, not opponent-adjusted:

EPA/play, passing efficiency (EPA/dropback), rushing efficiency (EPA/designed rush), play success, explosive plays,
sack rate, third-down conversion, red-zone TD rate, points per drive.

## What is already known (stated before testing)

- **Phase 8 already tested EPA/dropback, EPA/rush, success rate and red-zone TD rate as pick-model features, and they failed.**
  They were added to the live line-movement model (`docs/phase8_efficiency_report.md`).
- **Projection v6 added the same four metrics to v1, opponent-adjusted, and failed** (`docs/projection_v6_report.md`).
  It did not beat v1 or v3 on 2022–2024, and it had no edge against the close.
- **New here:**
  - all nine metrics together, including explosive rate, sack rate, third down and points per drive;
  - the owner's definitions (raw season-to-date, not opponent-adjusted);
  - a standalone model that is not built on v1;
  - 10,000 Monte Carlo simulations per game.
- **Expected outcome:** about as accurate as v1, and no reliable edge against the market. Reported either way.
- **About the 10,000 simulations:** v1 and v3 already compute the score distribution exactly, which equals
  infinitely many simulations. 10,000 draws approximate that to within about ±0.5 percentage points on a cover
  probability. The simulations are run because they were asked for, not because they are expected to add accuracy.

## Metrics (nflverse play-by-play, one row per team per game, offense view; defense = what it allowed)

- **Eligible plays:**
  - `play_type` in {pass, run}, which excludes kneels, spikes, no-plays and conversion attempts;
  - `two_point_attempt == 0`;
  - `epa` not null.
  - There is no garbage-time or neutral-situation filter, because the owner's season statistics use all plays.

| Metric | Definition |
|---|---|
| `epa` | mean EPA over eligible plays |
| `pass` | mean EPA per dropback (`qb_dropback == 1`: attempts, sacks, scrambles) |
| `rush` | mean EPA per designed rush (`play_type == run`, `qb_scramble == 0`) |
| `sr` | share of eligible plays with `success == 1` |
| `expl` | share of eligible plays that are a dropback gaining ≥ 20 yards or a designed rush gaining ≥ 10 yards |
| `sack` | sacks per dropback |
| `third` | third-down conversion rate: eligible plays with `down == 3`, converted if `third_down_converted == 1` |
| `rz` | share of drives with `drive_inside20 == 1` that end in a touchdown (`fixed_drive_result == "Touchdown"`) |
| `ppd` | offensive points per drive |

- **Points per drive, details:**
  - A touchdown drive scores 6 plus its conversion (1 for a good extra point, 2 for a successful two-point try).
  - A field-goal drive scores 3. Every other drive scores 0.
  - Drives whose only scrimmage plays are kneels are excluded.

## Season-to-date values (point in time)

- **Pooling:** for a game in week *w*, each team's offensive value of a metric pools every eligible play or drive
  from its earlier regular-season games **in the same season**. It is a pooled rate, not a mean of game means.
  The defensive value pools what it allowed.
- **No opponent adjustment and no prior-season carry-over**, as in the owner's definitions.
- **Centering:** each value is centered by that metric's league mean over the previous full regular season, to remove
  era drift. No current-season future data is used.
- **Scope:** regular-season games in weeks 3–18. Live picks start in week 3, and every team then has at least
  two games. A game is dropped if a team has no prior play of some type (for example, no red-zone drive yet). The
  number dropped is reported.

## Model

- **Rates:**
  - For each team-game: log λ_TD = a + b·home + Σ βᵢ·xᵢ, and the same form for λ_FG.
  - **x** is 18 features, standardized on training data: the team's 9 offensive values and the opponent's 9
    defensive values (what the opponent allows).
  - Both rates are fit as unpenalized Poisson regressions on the team's touchdowns and field goals (nflverse team
    stats, as v1).
- **Extra points:** the extra-point and two-point rates per touchdown are the training-period league rates.
- **Simulation:**
  - 10,000 games per matchup, NumPy seed 20261102.
  - Each team draws TDs ~ Poisson(λ_TD), a conversion per TD (0, 1 or 2 points) and FGs ~ Poisson(λ_FG).
  - The two teams are independent, as in v1.
- **Outputs:**
  - projected scores (simulation means);
  - projected margin and total;
  - P(home covers) and P(away covers) for any line.
- **Pick:** the side with the higher cover probability. Pushes are ignored.

## Training and testing

- **Train:** 2006–2021, weeks 3–18. There is no hyperparameter to tune.
- **Test A:** 2022–2024, weeks 3–18. Compared with the nflverse close and with v1 (walk-forward, as frozen):
  - ATS against the close;
  - margin MAE and total MAE (the close and the closing total are the market's prediction);
  - straight-up winner rate;
  - margin log-likelihood (from simulation frequencies, floored at 1/10,000).
- **Test B:** 2025, weeks 3–18.
  - The same measures.
  - ATS against the CBS open, in a paired comparison with the live model's picks (`data/backtests/holdout2025_games.csv`).
- **2026 live, weeks 3–8:**
  - On games with an official pick: v7's record against the pool line vs the official pick.
  - Per-game score accuracy vs the logged v1 and v3 projections.
  - 2026 play-by-play is used only up to each game, as everywhere else.

## Validation checks (before results are read)

1. **Point in time:** for 2 seeded games per season (2006–2025), rebuilding the features after deleting every play
   from that game's week onward gives identical features.
2. **Simulation reproduces the model:** the simulated mean points match the analytic means λ_TD·(6 + conv) + 3·λ_FG
   within 0.1 points on average.
3. **Sanity:** on training data, the fitted model's mean projected points per team-game are within 0.5 of the
   actual mean, and the end-of-week-18 values of `ppd` correlate with season points per game at > 0.8.

## Decision rules (fixed in advance)

- **Track v7 as a comparison projection** only if its Test A margin MAE is lower than v1's **and** its Test A ATS
  against the close is above 50% with z ≥ 1.0. Otherwise, record it as tested and not tracked.
- **The live pick changes** only if, on Test B plus 2026, v7 beats the live model against the CBS open or pool line
  by z ≥ 1.96 (paired, on games where they differ). This is the same bar as every earlier model.
- Every number is reported, including failures.
