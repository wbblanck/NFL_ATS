# Preregistration (DRAFT, not frozen): does the pregame EPA lineup score add out-of-sample accuracy beyond team form?

Status: research only, not validated. This draft is not in force until Will approves it, releases data, and the frozen configuration file below is written and committed before any confirmation data is loaded. Nothing in it touches the live pipeline, G1, or picks.

## Question

Does a pregame lineup score built from the frozen estimation-v2 player ratings reduce out-of-sample squared error for team-game EPA per dropback, beyond the strongest team-only baseline?

## Data (decision needed)

- Primary: 2022-2025 regular season, about 2,150 team-games, loaded once. These seasons are locked; this needs Will's explicit release.
- Secondary, if wanted: 2026 weeks 10-18 prospective, with the configuration frozen before those games. 2026 participation is not published, so ratings would stay as of the end of 2025. About 270 team-games, so it can only be a consistency check.
- 2019-2021 are used and are not scored again for confirmation.

## Frozen before loading confirmation data (written to `g2_confirmation_config.json`, hash recorded)

- Ratings: `g2-onfield-ridge-v2-prior`; pressure and EPA-per-attempt tables; ridge strength 100; half-life 730; walk-forward by week; no change to settings after seeing confirmation data.
- Score: S = z(passing shift from the EPA table: QB + target-share-weighted receivers + DB and LB coverage) + z(pressure shift: OL + DL + LB rush). Component means and SDs for the z-scores are the 2019-2020 values, stored in the config file, not recomputed on confirmation data. Thin thresholds 300 and 150, unseen players set to zero, snapshot cutoff kickoff minus 20 minutes.
- Baseline B1: team form with half-life 6 and prior weight 2 (offense and defense), coefficients refit walk-forward. Baseline B2 (stronger): B1 plus a second form window (half-life 24), home field, and prior-season team EPA; windows chosen on 2019-2020 only and stored in the config file. Every comparison is reported against both; the primary comparison is against whichever has lower out-of-sample error in the confirmation data.

## Primary test

Walk-forward by week: each week's team-games are predicted from coefficients fitted on all earlier confirmation-period team-games (starting week 7 of 2022) for baseline and baseline plus S. Statistic: mean weighted squared-error difference (baseline minus baseline plus S), weights = dropbacks. Uncertainty: game-cluster bootstrap (10,000 draws), week-block bootstrap as a check. No two-way cluster subtraction estimator.

Pass (all required):
1. The error difference is positive, with the game-cluster 95% interval excluding zero and the week-block interval excluding zero.
2. The fitted coefficient on S is at least +0.010 EPA per dropback per SD.
3. The difference is positive in at least 3 of the 4 seasons.

Pass means the lineup score earns a further preregistered test (including against the closing line), nothing more. Fail means the lineup track is closed for these inputs.

## Secondary (reported, Holm over three)

Passing shift alone; pressure shift alone; evidenced-only score (slots below thresholds set to zero). Also reported without a pass rule: actual-lineup upper bound, coefficient by season, and strata by share of evidenced slots.

## Required reporting

Players with meaningful pregame evidence per season; share of unseen and thin lineup slots by group; distribution of standard errors; score reliability (labelled as a spread measure, not validity); component correlations with the form residual; comparison with B1 and B2 side by side; separation of player-specific effects, group-level prior terms and uncertainty.

## Power (rough, my arithmetic)

With 2022-2025 and an SE near 0.009, power is about 60% for a true +0.020 per SD and about 35% for +0.014. A fail therefore cannot rule out small effects; it would say the effect is not large enough to detect with four seasons. Will should decide whether that is an acceptable test before releasing the seasons.

## Not tested here

Betting value against the market, context factors (coaching, scheme, continuity, motivation), assignment-level matchups. Deviations from this document will be listed in the report.
