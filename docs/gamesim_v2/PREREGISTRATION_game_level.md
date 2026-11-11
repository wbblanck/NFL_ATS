# Generation 2 game-level lineup test: preregistration

Written 2026-11-11, before any team-game outcome is joined to a lineup score. Follows `PREREGISTRATION.md` (periods, locked holdout 2022-2025 unchanged). Research only.

## Question

Does the pregame expected-lineup shift (from the snapshot and the walk-forward player effects) predict a team's passing offense in a game beyond team form that was known before the game?
This is the premise test before any drive or game engine is built. It is not an ATS test and uses no lines.

## Unit and period

Team-game offense, 2021 regular season (544 team-games, validation season). Team form is built from 2018 on. 2022-2025 are not loaded. One run, no tuning.

## Outcomes

Primary: **EPA per dropback** of the offense in that game (pbp `epa`, dropbacks with participation, penalty plays excluded as in the dropback table).
Secondary (mechanism): pressure-or-sack rate, completion rate per attempt.

## Predictors, all known at the cutoff

- **Team form** (the aggregate baseline, same spirit as G1's team factors): for the offense, its decayed mean of that outcome over its previous games, and for the opponent defense its decayed mean of the same outcome allowed. Half-life 6 games, carried across seasons from 2018, shrunk to the league mean of all earlier plays with 4 pseudo-games. Chosen now, not tuned.
- **Lineup shift** from the pregame snapshot (players with `p_active >= 0.5`; top 5 OL, 4 DL, 3 LB, 4 DB by snap share when active; the top quarterback; receivers weighted by their share of the team's targets in its previous 8 games), using each player's effect as estimated before that game's week, missing effects set to 0:
  - `P` = sum of OL effects of the offense plus DL and LB effects of the defense (pressure logit shift, positive = more pressure).
  - `C` = QB effect + target-share-weighted receiver effects + DB and LB effects of the defense (completion logit shift, positive = more completions).
  - `S` = z(C) + z(-P), z-scored over the 2021 team-games. Positive S means a better pass offense is expected.

## Tests

Weighted least squares (weight = dropbacks), outcome on form_off, form_def and S. Confidence interval by game-cluster bootstrap (2,000 resamples, seed 7), since two team-games share each game.
- **G1 (pass rule):** the S coefficient is positive with a 95% interval above zero **and** leave-one-week-out weighted MSE falls when S is added to form (paired game-cluster bootstrap interval of the MSE difference below zero).
- Secondary, reported not gating: the same two tests with S replaced by `-P` for pressure rate and by `C` for completion rate; and the S correlation with the form-only residual.
- Descriptive: the S coefficient as the change in outcome for one standard deviation of S.

## Power, stated in advance

544 team-games with a game-to-game standard deviation of EPA per dropback of roughly 0.3-0.4 can detect only a lineup effect of a few hundredths of EPA per dropback per standard deviation of S. The play-level gains found earlier (about 0.3% of log loss) imply an effect well below that. A failure therefore means **no evidence in one season**, not no effect; a pass would be a first sign, not a finding. Either way nothing here is a claim about picks.

## Decision rule

Pass: G1 holds for EPA per dropback. Then Will decides whether to widen to game margin and ATS on proxy lines (new preregistration, locked seasons untouched).
Fail: report that the pregame lineup shift adds nothing detectable at the game level on 2021, and recommend against building the full engine on these inputs.
