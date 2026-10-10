# FTN play-charting shadow model: pre-registration

Written before any FTN feature was computed or graded. At the time of writing, no FTN data had been loaded for this
test. Question: do play-charting features (blitzes, play action, motion, screens), added to a cover model, predict
closing-line covers better than the closing line alone, out of sample?

This is a shadow test. It changes no pick. The live model stays frozen, and nothing here feeds the 2026 pool picks.

## Data

- **FTN charting:** nflverse `load_ftn_charting`, seasons 2022 onward. Joined to play-by-play on `nflverse_game_id`
  and `nflverse_play_id`. The source and its 2026 coverage come from another project's handoff and are not yet checked
  here.
- **Grading line:** nflverse `spread_line` (positive = home favored), the same closing line as the bettable record.
  Pinnacle and the AusSportsBetting closes are not used.
- **Outcome:** home covers the closing spread. Pushes are refunded and excluded.

Pre-grading checks. Each is a check, not a result, and each must pass before the test runs:
1. FTN loads for 2022–2025 and for the 2026 weeks already played.
2. At least 99% of plays join to play-by-play.
3. Record the lag from kickoff to when a game's charting appears. In 2026, a game is shadowed only if its prior
   games' charting is present at lock. Otherwise it is logged as "no shadow prediction".

## Features (fixed now)

Each team-game value uses only earlier games, so there is no look-ahead. Each is shrunk toward the league mean with
k = 8 team-games.

1. Defensive blitz rate: share of the defense's dropbacks with 5 or more pass rushers (`n_pass_rushers`; the column
   definition is to be confirmed in check 1).
2. Offensive play-action rate: share of plays with `is_play_action`.
3. Offensive motion rate: share of plays with `is_motion`.
4. Offensive screen rate: share of plays with `is_screen_pass`.

Model inputs for each game: the home-minus-away difference of each feature, plus the closing home spread. The
baseline is intercept only.

## Model and tests

- **Model:** L2 logistic regression, penalty λ = 1.0, fixed. Walk-forward by season: each test season is fit on every
  earlier season from 2022. The 2023 fit therefore uses only 2022, which is thin. This is accepted and stated here.
- **Test seasons:** 2023, 2024, 2025. About 850 games in total.
- **Primary test:** out-of-sample log-loss difference, shadow minus intercept-only baseline, pooled over the three
  test seasons. Paired bootstrap by week, 10,000 draws, 95% interval.
- **Primary decision:** the shadow model passes only if the interval's upper bound is below 0 (lower log loss).
  A pass would justify a separate pre-registered test on 2026 shadow predictions. It would not change picks on its own.
- **Secondary, descriptive only:** the shadow model's side bet at the closing line at -110. Record with Wilson 95%
  interval, against break-even 52.38%. No decision rule.
- **2026 shadow:** each week's predictions are logged before lock and graded after. Report the record and the
  log-loss difference against baseline. No decision rule.

## Expectation (stated before running)

I expect the primary interval to include 0. Earlier tests in this project found that rating and pattern features did
not beat the closing line. A true 2-point edge needs about 5,900 bets to confirm at 80% power, and this test has about
850 games. A pass would be a surprise and would need checking before anything is adopted.

## Decision and next steps

- Live picks do not change, whatever the outcome.
- If the primary test passes: pre-register a confirmation on 2026 shadow predictions, before any use in picks.
- If it fails: keep logging the 2026 shadow predictions for the record, then retire the model.

## Limits

- **Licence:** the handoff reports FTN charting as CC-BY-SA 4.0, credited to FTN via nflverse. Not yet checked. Keep
  derived data in this private repo, or credit it and share it under the same licence.
- **Restatements:** the provider may correct charting after the fact. The shadow log, not the later data, is the
  record of what was known at lock.
- **Scope:** four features only. Adding any feature is a new registration.
- **Multiplicity:** one primary test. The secondary results are descriptive.
- **Not in scope:** nflverse participation, weather, Action Network lines, and any opposite-side bet.

## Amendment 1 (dated 2026-10-10, before any grading)

Reason: the registration left the denominators undefined. Also, `date_pulled` in the FTN data records nflverse
rebuild times, not when charting appeared, so check (c) can't be measured from it. The definitions below were set
after the pre-grading checks, which looked at the distributions of the feature columns. No game outcome was examined
for this amendment.

Changes (definitions only):
1. **Dropback** means nflverse `qb_dropback` = 1, which includes sacks and scrambles.
2. **Blitz rate** is the share of dropbacks with `n_pass_rushers` of 5 or more. Dropbacks with `n_pass_rushers` = 0
   (0.8% of dropbacks) or above 11 (two rows) count as missing and are removed from both numerator and denominator.
3. **Play-action rate** is the share of dropbacks with `is_play_action` set.
4. **Screen rate** is the share of dropbacks with `is_screen_pass` set.
5. **Motion rate** is the share of offensive plays (`play_type` run or pass) with `is_motion` set.
6. **Check (c)** is measured by a weekly log, `docs/evidence/ftn/lag_log.csv`, written by
   `scripts/ftn/lag_snapshot.py` and started 2026-10-10. The log records counts only, not FTN play rows. The 2026
   eligibility rule is unchanged: a game is shadowed only if its prior games' charting is present at lock.

Unchanged: the hypothesis; the purpose of each feature; the shrinkage (k = 8); the model (L2 logistic, λ = 1.0,
walk-forward from 2022); the test seasons; the primary decision rule; the shadow-only rule; and the expectation.
