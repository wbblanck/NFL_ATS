# Projection Model v6 (`proj-epa-v6`): Pre-registration

Committed **before** any v6 feature was computed or any v6 result seen.

## What the user asked for

"I want to test another model. It uses the original model but with EPA differentials and efficiency metrics."

- **"The original model"** is read as `proj-poisson-v1`, the first score projection. It rates teams only
  from touchdowns and field goals scored and allowed.
- **v6 keeps v1 unchanged and adds play-level efficiency:** EPA per play and success rate, opponent-adjusted,
  plus red-zone finishing.

## What is already known (stated before testing, so the result can't be spun)

- **Phase 6 tested a single EPA feature against the pick model and failed.** That feature was net opponent-adjusted
  EPA/play, added on top of the market-based pick model.
  - It correlated 0.79 with the market spread and 0.02 with the part of the margin the market missed.
  - v6 is a different question. It tests whether efficiency improves the **score projection** over v1, and
    whether the improved projection then does anything against the line.
- **Expected outcome:**
  - v6 probably projects margins better than v1. Play-level efficiency is known to predict future results
    better than points.
  - It will probably **not** beat the market. v1 and v3 both lost to the closing line on accuracy, and
    phase 6 found the market already prices EPA.
  - Both outcomes are reported either way.
- **Relation to the stop rule:** the v5.1 stop rule ended the *projection-distribution* track (v4–v5.1), which
  changed how scores are distributed. v6 changes the *inputs* to v1's expected scores. It is a new, separately
  pre-registered test, and it gets one attempt under these rules.

## Model

- **Base:** `proj-poisson-v1`, unchanged: walk-forward Poisson TD and FG rates (H = 8 weeks, λ = 5, frozen),
  with extra points and two-point tries as in v1, and an exact convolution for the margin.
- **v6:** each team's expected TDs and FGs are multiplied by exp(β·x), using the features x below.
  - β is estimated separately for TDs and for FGs, by Poisson regression with log λ_v1 as an offset, on
    training seasons only.
  - β = 0 gives v1 exactly.
  - Because v1's rate is the offset, β measures what efficiency adds **beyond** what v1's scoring-based
    ratings already contain.

## Play data and filters (nflverse play-by-play, regular season and postseason, 1999+)

- **Plays counted:** `pass == 1` or `rush == 1`, excluding `qb_kneel`, `qb_spike` and two-point tries.
- **Garbage time removed:** plays with win probability `wp` outside [0.10, 0.90], or in the final 120 seconds of a
  half (`half_seconds_remaining ≤ 120`), are excluded. This is the rbsdm.com convention.
  - `wp` is nflfastR's model without the Vegas line (`vegas_wp` is not used), so no betting market enters v6.
  - The share of plays removed is reported.
- **Dropback play:** `qb_dropback == 1` (passes, sacks, scrambles). **Designed rush:** `rush == 1` and
  `qb_dropback == 0`.

## Per-game metrics (offense view; the defense's value is what it allowed)

| Metric | Definition |
|---|---|
| `db_epa` | mean EPA per dropback |
| `rush_epa` | mean EPA per designed rush |
| `sr` | success rate over all counted plays (`success == 1`, i.e. EPA > 0) |
| `rz_td` | share of red-zone drives that end in a touchdown: drives with `drive_inside20 == 1`, TD if `fixed_drive_result == "Touchdown"`, with no garbage-time filter (drive outcome, not play efficiency) |

A team-game with no plays of a type (e.g. no red-zone drive) contributes no update for that metric.

## Ratings (built only from games before the one being rated)

- **Centering.** Each per-game value is centered by that metric's league mean over the **previous** full season.
  This keeps metrics comparable across eras without using the current season's future games.
- **Opponent adjustment.** A team's offensive game value is adjusted by subtracting the opponent's *pre-game*
  defensive rating for the same metric, and vice versa. This is the same method as `features/efficiency.py`
  (phase 6).
- **Recency.** Each rating is an exponentially weighted mean with half-life *h* games, across seasons.
- **New season.** At each new season, ratings shrink by a factor (1 − *s*) toward 0.

## Features (8 per team-game: the team's offense against the opponent's defense)

- **Features:** `off_db`, `off_rush`, `off_sr`, `off_rz` (the team's offensive ratings) and `def_db`, `def_rush`,
  `def_sr`, `def_rz` (the **opponent's** defensive ratings, i.e. what it allows; higher means worse defense).
- **"EPA differential":** in the game margin, the home team's offense-vs-defense matchup is set against the away
  team's. The model therefore works on EPA differentials without a separate difference feature.

## Hyperparameters (chosen without any test-season outcome)

- *h* ∈ {4, 8, 16} games and *s* ∈ {0.3, 0.6}, 6 combinations.
- **Inner validation, training seasons only:** fit β on 2006–2016 and score the margin log-likelihood on
  2017–2021. The best combination is frozen, then β is refit on all of 2006–2021.

## Training and testing (same test blocks as v3, so all three models compare on the same games)

- **Train:** 2006–2021 regular season. Ratings warm up on 1999–2005.
- **Test A:** 2022–2024. Measures:
  - margin log-likelihood,
  - margin MAE vs the market close,
  - P(home wins) log loss,
  - ATS against the closing line, with a paired sign test vs v1 and v3.
- **Test B:** 2025. The same measures, plus ATS against the CBS open (half-point lines) and a paired comparison
  with the live model.
- **Diagnostics (reported, not decision inputs):**
  - correlation of (v6 line − market close) with (actual margin − market close);
  - accuracy on games where v6 and the close differ by ≥ 3 points;
  - fitted β with standard errors.

## Validation checks (must pass before results are read; failures are fixed and disclosed)

1. **Point-in-time.** Rebuilding a game's features after deleting every play and game at or after its kickoff gives
   the same features (tolerance 1e-12). Run on 2 seeded games per season, 2006–2025.
2. **β = 0 reproduces v1** exactly (unit test).
3. **Ratings are sensible.**
   - The top 5 and bottom 5 offenses and defenses by dropback EPA at the end of 2023 are listed.
   - Across 2006–2021, the correlation between each team's end-of-season net rating (offense minus defense, EPA
     metrics) and its season point differential is > 0.6.
4. **Coverage.** ≥ 99% of 2006–2025 regular-season team-games have all 8 features.
5. **Filter sanity (reported).** The share of plays removed as garbage time, and red-zone drives per team-game
   (expected about 3).

## Decision rules (fixed in advance)

- **v6 replaces v3 as the tracked projection** only if its Test A margin log-likelihood is higher than **both** v1's
  and v3's.
  - Otherwise v6 is recorded as tested and not tracked.
  - v3 stays tracked, and v6 is not wired into the live runs.
- **The live pick switches to v6 only if**, on Test B plus live 2026 games, v6's ATS against the league line or
  CBS open beats the live model by z ≥ 1.96 **and** v6 has lower log loss. This is the same bar as every earlier
  model.
- Every number above is reported, including failures.
