# Score-Projection Model (tracked comparison): Pre-registration

Committed **before** any result from this model was computed.

## Purpose

This is a team-strength model that projects each team's score, as the user
requested ("we won't know what doesn't work till we try it"). It runs as a
**tracked comparison**. Its projections and picks are recorded every week and
graded against the league line. **It does not make the live pick** unless the
switch rule below is met.

## Model `proj-poisson-v1`

1. **Data (point-in-time):**
   - nflverse `team_stats`, regular season 1999+: touchdowns per team-game
     (passing + rushing + special teams + defensive) and field goals made.
   - Scores and home/away from the schedules.
   - A game's ratings use **only games that kicked off before it**.
2. **Ratings: two Poisson regressions with time decay and ridge shrinkage.**
   - log E[TD] = μ + h·home + att_TD[team] − def_TD[opponent]
   - log E[FG] = ν + g·home + att_FG[team] − def_FG[opponent]
   - Game weight = 0.5^(games-ago / H), counted in weeks across seasons, with
     an extra ×0.5 per season boundary.
   - A ridge penalty λ pulls team terms toward 0.
3. **Scores:**
   - TD ~ Poisson, FG ~ Poisson.
   - Extra points ~ Binomial(TD, p_xp); 2-point tries succeed with
     probability p_2 per TD.
   - p_xp and p_2 are league rates from training data.
   - Points = 6·TD + XP + 2·(2pt) + 3·FG.
   - The two teams are independent.
   - The margin distribution is computed **exactly** by convolution, so there
     is no Monte Carlo error. Monte Carlo (50,000 draws) is used only in a test
     that checks the exact method.
4. **Outputs:**
   - projected score per team (mean) and median margin,
   - the model line,
   - P(home covers S) for any half-point line,
   - pick = higher-probability side.
5. **Hyperparameters:**
   - H ∈ {8, 16, 32} weeks and λ ∈ {1, 5, 20}.
   - Chosen once, by log loss of P(home wins) on seasons **1999–2006 only**,
     with each week predicted from earlier games. They are then frozen.

## Evaluation

- **Primary:** walk-forward over 2007–2021 against the SBRO open, the same
  target as every other phase. Measures:
  - ATS W-L with SE,
  - log loss of P(cover),
  - MAE of the projected margin **vs** the MAE of the market close.
- **Comparison:** the live model (`shifted`, which uses the market) on the
  same games.
- **Confirmation:** 2025 with CBS opens, trained through 2024.
- **Diagnostics:**
  - dispersion of the TD and FG counts against Poisson,
  - accuracy on games where the model line and the market differ by 3 or more
    points.

## Switch rule (fixed in advance)

- `proj-poisson-v1` replaces the live pick **only if**, on the primary test,
  its ATS win rate beats the live model's by more than the combined SE
  (z ≥ 1.96) **and** its log loss is lower.
- Otherwise it stays a tracked comparison. Its weekly picks and projected
  scores are archived in `data/predictions/projections.csv` and graded in the
  live record.
- An end-of-season review uses the same disagreement rule as the key-number
  shadow (one-sided z ≥ 1.645).
