# Estimation v2: informative priors and an EPA outcome (development, 2018-2020)

Status: development only. Plan in `PREREGISTRATION_estimation_v2.md` (committed before any scoring). Nothing here is a validated result. 2021 was not touched again; 2022-2025 stay locked. No change to the live pipeline, G1, or picks.

## Headline

Priors from draft round and years of experience, and an EPA-per-attempt outcome, do not improve play-level prediction. The first completion result (log loss -0.0050) was a leak and is withdrawn. At the team-game level the EPA-based lineup score looked better than before with the two-way standard error (pooled z 2.5 to 3.1), but that standard error is unreliable for these scores; with a game-cluster bootstrap the same scores have z 1.6 to 1.7, and the gain is only in 2020, which is also the season the player models were tuned on. Under the bootstrap the one stronger result is different: the completion-rate predictions from the v2 completion table (z 3.2 to 3.5, Holm 0.01 to 0.02 within that variant). Both are leads for a fresh preregistered test, not findings. See the audit section at the end (2026-11-12).

## Data defect found and fixed (first run withdrawn)

The first run showed completion log loss -0.0050 (interval -0.0059 to -0.0041) for priors vs the frozen player model. Checks:

- The same pipeline with the prior columns switched off matched the frozen player model to within 0.000002 log loss (difference 0.0000011, interval -0.0000002 to +0.0000024), so the pipeline was not the cause.
- Switching prior columns on by group: receivers alone -0.0040; QB -0.0002; DB -0.0001; LB +0.0003.
- 2,018 attempts in 2016-2020 have no recorded target, and all 2,018 are incomplete. The receiver prior columns count the targeted receiver, so they were zero exactly on those plays and acted as a "no target, so incomplete" flag. The target is only known after the throw, so this is leakage.

Fix: completion and EPA use attempts with a recorded target only (85,972 and 85,971 plays). The control is now the same pipeline with no prior columns on the same plays. First-run numbers are kept in `manifests/estimation_v2_first_run_leaked.json` and are not to be cited. Pressure does not use the target and is unaffected.

## M1 and M2: play-level out-of-sample error (walk-forward, 2019 and 2020)

| Outcome | Comparison | Plays | Difference | 95% interval |
|---|---|---|---|---|
| Pressure (log loss) | priors minus no-prior control (same pipeline) | 37,752 | +0.00013 (worse) | -0.00040 to +0.00065 |
| Completion (log loss) | priors minus no-prior control | 34,162 | -0.00025 | -0.00063 to +0.00011 |
| Completion 2019 / 2020 | same | 16,976 / 17,186 | -0.00047 / -0.00004 | -0.00098 to +0.00006 / -0.00054 to +0.00043 |
| EPA per attempt (squared error) | priors minus no priors | 34,161 | +0.00002 | -0.00160 to +0.00161 |
| EPA | priors minus context only | 34,161 | +0.0063 (worse) | -0.0009 to +0.0134 |
| EPA | priors minus team factors | 34,161 | +0.0084 (worse) | +0.0021 to +0.0142 |

Mean squared error on EPA: context 2.3235, team 2.3214, player no priors 2.3297, player with priors 2.3298. The player EPA model is worse than team factors out of sample, and the interval excludes zero. Positive differences mean the priors or player model had more error.

## M3: split-half repeatability of player effects (players with at least 150 plays, 400 for pressure, in both halves)

Total effect = group-bucket term plus player deviation. Receivers: 41 players. Completion halves 2016-2018 vs 2019-2020; pressure halves 2018-2019 vs 2020.

| Group, outcome | No priors r | With priors r | Deviation only, with priors r |
|---|---|---|---|
| OL, pressure (88 players) | 0.012 | -0.140 (interval -0.340 to 0.071) | -0.032 |
| Pass rush DL/LB, pressure (61) | 0.219 | -0.012 | 0.141 |
| QB, pressure (18) | 0.670 | 0.642 | 0.529 |
| Receivers, completion (41) | 0.237 | 0.391 (interval 0.095 to 0.624) | 0.245 |
| DB, completion (190) | -0.042 | -0.046 | -0.038 |
| QB, completion (35) | 0.539 | 0.364 | 0.541 |
| Receivers, EPA (41) | 0.277 | 0.323 | 0.277 |
| DB, EPA (190) | 0.033 | 0.070 | 0.031 |
| QB, EPA (35) | 0.422 | 0.291 | 0.433 |

The receiver rise from 0.24 to 0.39 on completion comes from the group-level experience and draft terms, not from the player-specific deviation, which repeats no better (0.245). With 41 players the two intervals overlap almost entirely (-0.08 to 0.51 vs 0.09 to 0.62), so the rise is within noise. It did not produce better out-of-sample completion log loss (M1). Correction (2026-11-12): an earlier version of this paragraph and of the summary said the receiver draft terms were 0.21 to 0.32 logit; those numbers came from the leaked first-run population. On the clean population the receiver terms are small (draft round 1 -0.04, 2 +0.06, 3 +0.03, 4-7 +0.00; experience 0 years -0.09, 1 year -0.05, 2-3 years +0.00 logit). See `RECEIVER_AND_D5_DIAGNOSIS.md`.

## M4: lineup-score reliability and thin slots (1,024 team-games, 2019-2020, 31,570 lineup slots)

Reliability = variance of the score over variance plus mean squared standard error.

| Score | Frozen v1 tables | v2 with priors | v2 with EPA passing score |
|---|---|---|---|
| Completion / passing shift | 0.337 | 0.396 | 0.450 |
| Pressure shift | 0.365 | 0.479 | 0.479 |

Slots: 65.5% have meaningful evidence; thin share by group (v2 completion table; the EPA table differs by at most 0.5 points): OL 14.9%, QB 6.6%, DB 4.1%, receivers 70.0%, rush DL 25.1%, rush LB 23.6%, coverage LB 10.1%. Zero-imputed (unseen) slots are 0.1%. Players with effects in lineups: 1,260 (2019), 1,499 (2020). Median standard errors of known slots, by table and unit: pressure groups (logit): OL 0.067, rush DL 0.075, rush LB 0.072. Completion table (logit): QB 0.063, receivers 0.096, DB 0.064, coverage LB 0.068. EPA table (EPA per attempt, a different unit that cannot be compared with the logit values): QB 0.051, receivers 0.123, DB 0.053, coverage LB 0.058. Earlier drafts quoted one range across both units.

Caution: this reliability measure rises when the priors add spread to the scores, whether or not the spread is signal. Pressure reliability rose 0.365 to 0.479 while the pressure M1 showed no gain and the OL split-half r fell. M3 and M1 are the better tests; M4 does not by itself show improvement.

## M5: team-game EPA per dropback on form plus lineup shift (form calibrated on 2019, pooled; z shown with the two-way team-and-week standard error used in the preregistered script, and below with a game-cluster bootstrap that the audit found more reliable)

| Score | v1 tables | v2 completion | v2 EPA passing shift |
|---|---|---|---|
| Combined (D1) coefficient per SD | +0.0137 (z 1.10) | +0.0158 (z 1.92) | +0.0197 (SE 0.0080, z 2.46, Holm over 18 tests 0.21) |
| Uncertainty-weighted (D4) | +0.0149 (z 1.22) | +0.0168 (z 2.08) | +0.0217 (z 3.06, Holm 0.04) |
| Actual lineup, upper bound (D10) | +0.0254 (z 1.79) | +0.0292 (z 3.35) | +0.0368 (z 4.16) |

D1 by season with EPA passing shift: 2019 +0.0078 (z 0.87), 2020 +0.0271 (z 1.76). With v1 tables: 2019 +0.0142, 2020 +0.0120. So the improvement is concentrated in 2020.

Reasons not to read this as evidence:
- Out-of-sample CV error change for the combined scores is about zero with intervals spanning zero (D1 EPA -0.000105; D4 -0.000168).
- The evidenced-only score (D5) shows z 6.9 from a standard error of 0.0027, a third of its neighbours' and inconsistent with its CV change (-0.000112, interval -0.00069 to +0.00050). Diagnosed 2026-11-12 (`RECEIVER_AND_D5_DIAGNOSIS.md`): the two-way cluster formula (team plus week minus their intersection) nearly cancels to 7e-6 variance; every other method gives 0.009 to 0.0135 (z 1.4 to 2.1). The two-way z-statistics in this table are overstated, D1 included.
- Two-way clustering with two seasons is unstable for the v2 scores: D1 2019 SE was 0.0206 with v1 tables and 0.0090 with v2. With a game-cluster bootstrap (1,000 draws), pooled z for the v2 EPA table is D1 1.57, D4 1.74, D5 1.49, D10 2.88 (Holm over 18 tests 1.00, 1.00, 1.00, 0.07). For the v1 tables the two methods agree (D1 z 1.10 vs 1.11).
- 2020 was used to tune the player models; EPA tables inherit those settings; and I looked at three variants.
- The play-level EPA model is itself worse than team factors out of sample (M2).

Under the preregistered interpretation key (improvement means higher reliability and lower play-level error, not a significant M5), the result is: reliability up on the spread measure, play-level error not lower. Not an improvement.

## What this says, and what to do next

1. Draft and experience priors are not the missing ingredient. Pressure and completion are flat; the receiver split-half rise (0.24 to 0.39) is within noise and the clean-data prior terms are tiny.
2. EPA per attempt is too noisy for player-level fits at this sample size; it underperforms team factors.
3. Two leads, both development-only: (a) the EPA lineup score on team-game EPA, +0.020 per SD pooled, bootstrap z 1.6, concentrated in 2020; (b) the v2 completion table's QB and receiver shifts on team-game completion rate, +0.012 per SD, bootstrap z 3.2 to 3.5 (Holm 0.01 to 0.02 within the 18 tests of that variant; roughly 0.03 to 0.06 if multiplied by the three variants examined). Which of the two is primary has to be decided before anything is scored. A fresh test needs a new preregistration with fixed score definitions and a scoring period not yet used (2021 was spent for play and game level; 2022-2025 is locked and needs Will's explicit release).
4. Resolved (2026-11-12): the large drafted-receiver effect existed only in the leaked fit. On clean data drafted receivers complete +0.02 logit (about 0.5 points) more often than undrafted, matching raw rates (65.2% vs 64.6%).

Files: `scripts/gamesim_v2/estimation_v2.py`, `src/engine/gamesim_v2/players/abilities_v2.py`, `src/engine/gamesim_v2/validation/play_validation_v2.py`; `lineup_dev_2019_2020.py` now takes `G2_PRES`, `G2_COMP`, `G2_OUT` environment variables (defaults reproduce the earlier run). Manifests: `estimation_v2.json`, `lineup_dev_v2_completion.json`, `lineup_dev_v2_epa.json`.

## Audit, 2026-11-12 (Will asked for a full accuracy check)

What was checked and found:
- Every number in this report was compared with the manifests: M1, M2, M3, M5 values matched. Corrected here: the pressure interval (the pressure run was repeated with the current script, which now uses the same no-prior control as completion; the split-half numbers are identical, the interval moved from -0.00038/+0.00067 to -0.00040/+0.00065 because the bootstrap draws differ), the mixed-unit standard-error range, the headline and the stale receiver sentence.
- The leak numbers (receivers alone -0.0040, etc.) were first produced by a scratch script that was not in the repo. `scripts/gamesim_v2/prior_ablation.py` reproduces them: on all attempts, receivers alone -0.00404, QB -0.00022, DB -0.00009, LB +0.00025; on the clean population, receivers -0.00033, QB -0.00025, DB -0.00017, LB +0.00026.
- The frozen v1 lineup path was re-run with the edited script and reproduces the committed results exactly (all 18 pooled tests, coefficient and z, maximum difference 0.0).
- The full test suite passes (285 tests). No file outside the Gen 2 directories differs from `main`.
- Larger finding: the earlier frozen completion results used a population that includes no-target attempts. See `ERRATA.md`.
- All 18 pooled tests were recomputed with a game-cluster bootstrap for the three score variants (`robust_se_all_*.json`). Full list in `ERRATA.md`.
