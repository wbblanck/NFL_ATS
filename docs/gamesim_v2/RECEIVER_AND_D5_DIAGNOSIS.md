# Receiver draft effect, D5 standard error, and a tuning audit (development, 2016-2020)

Status: development only. No holdout data used. Scripts: `scripts/gamesim_v2/receiver_decomposition.py`, `scripts/gamesim_v2/d5_diagnosis.py`; manifests `receiver_decomposition.json`, `d5_diagnosis.json`.

## 1. Receiver draft-round effect: the large effect was part of the leak

The earlier report said drafted receivers completed about 5 points more often in the fitted models than their raw rates implied. That came from the first-run population, which still contained the 2,018 no-target attempts. On the clean population (85,972 attempts with a target, 2016-2020):

- Raw completion: drafted targets 65.17%, undrafted 64.63%. 80.2% of targets are drafted players.
- Logit coefficient for "drafted" with nothing else: +0.024 (about 0.5 points). Adding air-yards bucket, pressure, down, distance and shotgun: +0.024. Adding target position: +0.022. Adding quarterback fixed effects (QBs with 300+ attempts): +0.018. Adding offense and season dummies: +0.015.
- By position with context: WR -0.001 (50,723 targets), TE +0.069 (17,766), RB +0.044 (17,308). By season with context: -0.037, +0.079, -0.010, +0.083, -0.021 for 2016 to 2020, so the sign is not stable.
- Prior-term coefficients in the actual v2 completion fit (training 2016-2018, clean population): receivers draft round 1 -0.043, 2 +0.059, 3 +0.034, 4-7 +0.003; experience 0 years -0.093, 1 year -0.051, 2-3 years +0.004. Fitting each group's prior columns alone changes held-out log loss by: receivers -0.00033, QB -0.00025, DB -0.00017, LB +0.00026.

Conclusion: there is no draft-round effect worth modelling. The 0.21 to 0.32 logit figures should not be used anywhere. The only thing that remains is a small experience effect for rookies and second-year receivers (-0.09, -0.05 logit), and its held-out gain is -0.0003 log loss.

## 2. D5 standard error

Setting: v2 pressure table plus v2 EPA table, calibrated form (half-life 6, k 2), pooled 2019-2020, 1,024 team-games, outcome EPA per dropback.

| Score | Coefficient per SD | Two-way (team+week) | Team only | Week only | No clustering (HC0) | Game bootstrap | Week bootstrap |
|---|---|---|---|---|---|---|---|
| D1 combined | +0.0197 | 0.0080 | 0.0106 | 0.0101 | 0.0123 | 0.0127 | 0.0098 |
| D5 evidenced only | +0.0187 | 0.0027 | 0.0090 | 0.0090 | 0.0124 | 0.0135 | 0.0089 |

Cause: the two-way estimator is team variance plus week variance minus the team-by-week (observation-level) variance. For D5 these are 8.04e-5 + 8.14e-5 - 15.44e-5 = 0.73e-5, so the combination almost cancels and the square root is 0.0027. For D1 it is 6.4e-5 (SE 0.0080). Team and week clusters add almost nothing over the observation-level term (little within-cluster dependence), so the subtraction leaves a difference that is dominated by noise. Every other method gives 0.009 to 0.0135.

Implications:
- D5's z of 6.9 should be 1.4 to 2.1. It is an estimator artifact, not evidence.
- D1's z of 2.46 (coefficient 0.0197) is 1.55 with the game bootstrap, 1.60 with HC0, 1.86 with team clustering and 2.0 with the week bootstrap. The reported two-way z-statistics for the v2 EPA score are overstated. The same estimator gave an SE of 0.0124 for the v1 score, so the apparent improvement in significance between v1 and v2 is partly this artifact. D4's z of 3.06 was not recomputed.
- Each game contributes two team-games that share weather, pace and game script, so the game cluster is the natural one. Proposal for confirmation: game-cluster bootstrap as primary, week-block bootstrap as a check, and no multiway subtraction estimator.

Power consequence (rough, my arithmetic): with a game-bootstrap SE of about 0.0127 at 1,024 team-games, 2022-2025 (about 2,150 team-games) gives an SE near 0.0088. For a true effect of +0.020 per SD that is about 60% power, and about 35% power at +0.014. The earlier statement that about 1,300 team-games would reach 80% power used the optimistic two-way SE and should be dropped.

## 3. Tuning audit: which decisions used which seasons

| Decision | Seasons that informed it | Where fixed | Comment |
|---|---|---|---|
| Ridge strength 100 and decay half-life 730 days | 2020 development grid | `dev_grid_2020.json`, `g2_frozen_config.json` | Inherited by every later model, including EPA, which was not retuned (if anything this handicaps EPA) |
| Pressure training start 2018 | Data audit (label definition changes 2017 to 2018) | `DATA_AUDIT.md` | Not outcome tuning |
| Snapshot cutoff (kickoff minus 20 min), availability model | 2016-2021 snapshot diagnostics | `snapshot_manifest.json` | Pool recall and Brier checked on 2016-2021 |
| Validation gate and V1-V8 criteria | Written before scoring 2021 | `PREREGISTRATION.md` | 2021 scored once; 2021 results then shaped everything below |
| Lineup score definition (top-N by share, target-share weights) | Written before the 2021 game-level test | `PREREGISTRATION_game_level.md` | Same definition reused in 2019-2020 |
| Thin thresholds 300 (pressure) and 150 (completion) | Fixed in the 2019-2020 extension preregistration before its results | `PREREGISTRATION_lineup_dev_2019_2020.md` | Arbitrary, not tuned |
| Team-form baseline (half-life, prior weight k) | 2019 leave-one-week-out grid, then applied to 2019 and 2020 | `lineup_dev_2019_2020.py` | 2019 is in-sample for the baseline. v2 EPA run chose half-life 6, k 2 |
| Draft and experience buckets; EPA outcome; MINN thresholds | Chosen after the 2019-2020 diagnostics and the 2021 result were seen | `PREREGISTRATION_estimation_v2.md` (committed before scoring) | Design direction was informed by used seasons even though scoring followed preregistration |
| Which of three score variants to look at (v1, v2 completion, v2 EPA) | Chosen after seeing 2019-2020 results | Not preregistered as a family | Holm over 18 tests covers one variant, not all three |
| Null-target exclusion for completion and EPA | Found by checking an anomalous result | `ESTIMATION_V2_DEV.md` | Deviation from the preregistered population, documented |

Reading: play-level predictions for 2019 and 2020 are out-of-sample with respect to their own fits (walk-forward). The contamination is in design choices. 2018-2021 are all used. A confirmation test needs seasons that influenced none of the above: 2022 onward.
