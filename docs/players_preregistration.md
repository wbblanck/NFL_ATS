# Player-Availability Projection (v2): Pre-registration

Committed **before** any result from this model was computed. The user asked
for a 2025 test that uses depth charts and injuries.

## Model `proj-players-v1`

This is `proj-poisson-v1` (H = 8, λ = 5, frozen) with an availability
adjustment:

λ_TD(team) = λ_TD,v1(team) · exp(β_qb·qb_backup + β_off·off_out(team) + β_def·def_out(opponent)).

The same form, with its own β, applies to λ_FG.

## Features

| Feature | 2025 test (point-in-time) | Training 2012–2024 |
|---|---|---|
| `qb_backup` (offense) | 1 if the QB1 on the team's **last depth-chart snapshot before lock** (`dt` < kickoff − 15 min) is not the "established starter", **or** the established starter is Out/Doubtful on that week's injury report. The established starter is the QB with the most starts in the team's previous 4 regular-season games. | 1 if the recorded starter differs from the established starter. This is near point-in-time, because starters are usually known before lock; disclosed as a small look-ahead risk. |
| `off_out` | Number of the team's offensive starters (depth-chart rank 1 at RB, WR, TE, T, G, C) listed **Out or Doubtful** on that week's injury report, capped at 5 | Same, using the weekly depth chart `depth_team == "1"` |
| `def_out` (of the opponent) | Number of the opponent's defensive starters listed Out/Doubtful, capped at 5 | Same |

- **Injury reports:** the NFL's final game-status report (Out, Doubtful,
  Questionable) is published before the game, so the week's `report_status`
  counts as pre-game information.
- **Unverified:** whether nflverse ever revises a week's row after the game.

## Estimation

- β is fit **once** on 2012–2024, pooled, by Poisson regression of the actual
  TD (and FG) counts on the features, with log λ_v1 as an offset.
- λ_v1 is the walk-forward v1 rate for each game, using games before it
  only.
- β is then frozen for 2025.

## Test (2025, the only season with timestamped depth charts)

- Walk-forward by week, graded against the **CBS odds-page open**.
  - **Primary:** the 210 games with a half-point open.
  - Also reported: all games with an open.
- **Compared on the same games with:**
  - `proj-poisson-v1`,
  - the live model (`shifted`),
  - the user's 141/272 pace.
- **Also reported:**
  - margin MAE against the market close,
  - the fitted β with SE,
  - and, as a diagnostic, the games where `qb_backup` = 1.

## Honest limits, stated in advance

- One season is about 210–270 games, so the SE is about 3.4 pp. A 3-point
  difference between models is **not** distinguishable.
- This test can show whether player availability makes the projections more
  accurate. It cannot prove an edge.

## Decision rule

- The live pick switches only if `proj-players-v1` beats the live model on
  2025 by z ≥ 1.96 **and** has lower log loss. That is very unlikely with this
  sample size.
- Otherwise it joins the tracked comparisons, and is recorded weekly from
  2026 week 4 on.
