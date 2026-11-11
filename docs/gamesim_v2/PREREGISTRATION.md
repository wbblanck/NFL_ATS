# Generation 2 preregistration (sprint 1)

Written 2026-11-11 before any 2021 outcome was scored against the frozen models. Research only: no change to `final.py`, the pick
pipeline, G1 code or constants, or any recorded pick. Result files: `data/gamesim_v2/manifests/`. Nothing in this document is a claim of skill.

## What is being tested

Whether information about which players are on the field improves the prediction of individual passing plays beyond what team-level
(aggregate) factors, like G1's, already give. Two play-level models: **pressure** (was the quarterback pressured or sacked) and
**completion** (did a targeted pass complete). This is the first gate in the spec's order (audit, data, player ability, matchups). It says
nothing yet about game margins or ATS picks.

## Periods

| Period | Seasons | Use |
|---|---|---|
| Fit | 2016-2019 (completion), 2018-2019 (pressure; the label changes definition between 2017 and 2018, `DATA_AUDIT.md`) | Walk-forward training history |
| Development | 2020 | Ridge strength and decay half-life chosen here (done: `dev_grid_2020.json`, config frozen in `g2_frozen_config.json`) |
| Validation | 2021 | Frozen models scored once per the rules below |
| Locked holdout | 2022-2025 | Not loaded, scored or tuned on. Matches G1's confirmation span; G1 stays the registered baseline and G2 may not reuse these seasons for selection |

Disclosure: before this document, the availability table `p_active` was calibrated against 2016-2022 played/not-played flags (Brier 0.133-0.153 for 2016-2022).
That touched 2022 availability outcomes, not passing outcomes, and no choice depended on it. The snapshot builder now stops at 2021.

## Models and frozen settings

`g2-onfield-ridge-v1`: weighted ridge logistic regression, `logit P = intercept + context + sum of effects of players on the field`, one ridge penalty
per player group (partial pooling), training rows decayed by `0.5 ** (age_days / half_life)`, refit every (season, week) using only plays dated before the block.
Pressure: five OL, DL and LB on the field, QB. Completion: targeted receiver, QB, DB and LB on the field. Context terms are listed in `players/abilities.py`.
Variants compared (each at its own development-best setting, `g2_frozen_config.json`): **ctx** (context only), **team** (context + offense and defense team effects),
**player** (context + player effects), **both**.

Not modelled and so not tested: blocker-versus-rusher pairing, defender-on-receiver assignment, separation, route, formation, play call. Participation says who was on the field.

## Validation criteria (2021, all pre-specified)

Statistic: mean per-play log-loss difference with a game-cluster bootstrap (2,000 resamples, seed 7). Negative favours the second model.

| ID | Test | Pass if |
|---|---|---|
| V1 | pressure: player vs ctx | 95% interval upper bound < 0 |
| V2 | pressure: player vs team | point estimate < 0 |
| V3 | completion: player vs ctx | 95% interval upper bound < 0 |
| V4 | completion: player vs team | point estimate < 0 |
| V5 | calibration of the player variant, both models: logistic recalibration `logit(y) ~ a + b * logit(p)` | `0.85 <= b <= 1.15` and `abs(a) <= 0.05` |
| V6 | out-of-sample line gradient (pressure): quintiles of the summed OL effect on the field, as estimated before that play's week | observed pressure rate falls across the five quintiles in order, and Q1 minus Q5 has a bootstrap 95% interval above 0 |
| V7 | split-half reliability of effects: fit on 2018-2019 and on 2020-2021 separately (no decay), correlation of each player's effect across halves, players with 400 or more on-field dropbacks (pressure) or 150 or more (completion) in both halves | Pearson r > 0 with a Fisher-z 95% interval excluding 0, for OL, rushers (DL and LB together), QB in pressure; receivers, DBs, QB in completion (reported per group) |
| V8 | pregame signal: for each 2021 team-game, the OL plus rush effect sum of the expected lineup from the pregame snapshot (top 5 OL, 4 DL, 3 LB by expected share among players with `p_active` of at least 0.5) against that team-game's pressure rate minus the ctx model's expected rate | Spearman correlation has the expected sign (OL: more protection, less pressure; rush: more rush, more pressure) with a bootstrap 95% interval excluding 0. Reported alongside the same correlation using the actual lineup (upper bound) and the team-effect score |

Gate to build drive and game simulation on these models: V1, V2 and V5 pass for **pressure**. If V2 fails, the player-level pressure effects add nothing over team aggregates at the
play level, and the recommendation is to stop and say so. Completion results are reported either way. V3-V4, V6-V8 inform; they are not gates.

## Dependency-level expectations (written before the tests, `tests/gamesim_v2/`)

- Replacing one starting lineman with an elite one lowers the pressure probability; five elite linemen lower it more than one; a replacement-level lineman raises it.
- Adding a rusher (5 vs 4) and an elite rusher raise it. Five replacement linemen against five elite ones swing the probability by more than 0 and less than 0.5.
- An elite QB, a better receiver and a weaker secondary raise completion probability; pressure lowers it.
- Completion given the pressure state does not change when only the line changes (a line affects completion only through pressure), within Monte Carlo error.
- Same seed and version reproduce the same trace; extra draws in one random stream do not change another stream's draws; traces are causally ordered (a sack has no target).

## Sample sizes

2021: about 19,700 dropbacks and 18,600 pass attempts with a target. In 2020 the pressure player-vs-ctx gain was 0.0029 per play (interval -0.0042 to -0.0014),
so detecting effects of this size needs on the order of the full season; per-game effects are far below detectability.

## Decisions deferred (nothing below has been run)

**Game and ATS challenger.** Not started until the gate above passes and drive/game components are validated. Planned design, to be re-registered with dates and exact games before use:
- Grading line: the recorded CBS Tuesday pool line only. Where none exists (all seasons before 2025, and 2025 outside the weeks with captured lines), results are labelled proxy (nflverse closing line or AusSportsBetting open/close, local only) and are descriptive, never a skill claim.
- Comparators on identical games and identical lines: official pick, G1 simulator (G3 constants), Elo baseline, closing-line benchmark.
- Primary metric: correct sides against the frozen line, paired against the official pick on common games, one-sided binomial test on games where the two differ, Holm across the pre-named G2 variants. No skill claim before 256 graded games (existing rule).
- Final test: the locked 2022-2025 holdout, once, with proxy lines, plus forward shadow picks on 2026 weeks with actual CBS lines (week cut-off set by Will before the first shadow run).
- Exclusions: games without a pregame snapshot (e.g. week 1 with no earlier games), games with a quarterback change after the snapshot cutoff are kept and flagged, not dropped.
- Monte Carlo: simulations per game chosen so the standard error of the cover probability is at most 0.01.

**Open choice for Will.** Whether the forward shadow period should start now or after week 18 (batch 6 shares 2026 weeks 10-18).
