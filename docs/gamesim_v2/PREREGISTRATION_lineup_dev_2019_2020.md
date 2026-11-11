# Generation 2 lineup diagnostics on 2019-2020: development preregistration

Written 2026-11-11 before any 2019 or 2020 team-game outcome is joined to a lineup score. **Developmental, not confirmatory.** The 2021 test (`GAME_LEVEL_2021.md`) is spent and failed its rule; it is not reopened, and these results are never pooled with it as confirmation. 2022-2025 stay locked and are not loaded.
Disclosure: 2020 plays were used to choose the ridge strength and half-life of the player models (`dev_grid_2020.json`), so 2020 results are not clean for the player effects; 2019 is cleaner (training history only). Both are reported separately and pooled.

## Question

Is the weak lineup signal in 2021 because the sample was small, the player estimates are noisy, the snapshot lineups are wrong, the zero for unseen players hides information, or the effects are genuinely negligible?

## Data

Team-games of the 2019 and 2020 regular seasons (form from 2018). Player effects, snapshots and outcomes exactly as in the 2021 test. Effects are the walk-forward ones already on disk (fit only on plays before each week). Loading is restricted to seasons up to 2020.

## Team form, calibrated

The 2021 test used a priori form settings (half-life 6 games, 4 pseudo-games). Here form is also calibrated: half-life in {3, 6, 12, 24} games and shrinkage in {2, 4, 8} pseudo-games, chosen per outcome by leave-one-week-out weighted error of the **form-only** model on **2019**. The chosen setting is then used for 2020 and for the 2019 lineup increments (the lineup scores played no part in choosing it). Both a priori and calibrated form are reported.

## Lineup components (sign-aligned so positive means better for the offense)

Per team-game, from the pregame snapshot (`p_active >= 0.5`; top 5 OL, 4 DL, 3 LB, 4 DB by snap share when active, top QB, receivers weighted by prior 8-game target share), effects as of that week:
`ol` = minus the OL pressure effects; `rush` = minus the DL and LB pressure effects; `qb` = QB completion effect; `recv` = target-share-weighted receiver completion effects; `cov` = DB and LB completion effects (higher means weaker coverage). Players with no effect in that week's table get 0 and are counted as **unseen**; players with an effect but fewer than 300 (pressure) or 150 (completion) on-field plays are **thin**; the rest are **evidenced**.

## Diagnostics (all reported; none changes the 2021 rule)

| # | Predictor | Outcome(s) |
|---|---|---|
| D1 | Combined S = z(qb+recv+cov) + z(ol+rush), as in 2021 | EPA per dropback |
| D2 | Completion shift alone: qb+recv+cov | EPA, completion rate |
| D3 | Pressure shift alone: ol+rush | EPA, pressure rate |
| D4 | Uncertainty weighting: each shift divided by the square root of the summed squared standard errors of its slots, then combined as S | EPA |
| D5 | Evidenced-only: slots that are thin or unseen set to 0 | EPA; and the S coefficient split by team-games with above vs below median share of evidenced slots |
| D6 | OL only | pressure rate, EPA |
| D7 | QB only | completion rate, EPA |
| D8 | Receivers only (target-share weighted) | completion rate, EPA |
| D9 | Opponent defense only: rush (DL+LB pressure) and coverage (DB+LB completion) | pressure rate / completion rate, EPA |
| D10 | Upper bound: D1 recomputed with the players who actually played (share of the game's dropbacks on the field times the effect; receivers still by pregame target share) | EPA |

Interpretation key: D10 clearly better than D1 means the snapshot lineups lose signal; D10 and D1 both flat means the effects are small or noisy; D4 or D5 better than D1 means uncertainty and unseen players matter.

## Statistics

Weighted least squares (weight dropbacks, or attempts for completion rate) of the outcome on offense form, opponent defense form and the predictor. Standard errors by two-way cluster-robust variance (offense team and week), plus the game-cluster bootstrap from the 2021 test (2,000 resamples, seed 7). Leave-one-week-out weighted MSE change against the form-only model, paired by game-cluster bootstrap. Holm correction across all diagnostic coefficient tests (about 25), applied to two-way-cluster p-values. Results are by season (2019, 2020) and pooled.

## Required reporting

Number of distinct players with evidence per season; share of lineup slots that are unseen, thin and evidenced, by group; quantiles of the standard errors and on-field counts of slot players; reliability of the lineup score (variance of the score over variance plus mean summed squared standard error); the correlation of every component with the form-only residual.

## Interpretation limits

Estimates are exploratory. Nothing here selects features, thresholds or architecture for any confirmatory test without a new preregistration on data not yet scored, and 2022-2025 are reserved for that. No ATS or line data is used.
