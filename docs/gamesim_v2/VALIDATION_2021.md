# Generation 2 play-level validation, 2021 (preregistered tests V1-V8)

Run 2026-11-11 with the settings frozen in `data/gamesim_v2/manifests/g2_frozen_config.json` (committed before this run, `PREREGISTRATION.md`).
Script `scripts/gamesim_v2/validate_plays.py`; numbers in `data/gamesim_v2/manifests/validation_2021.json`. Validation season 2021 only: 19,724 dropbacks (pressure)
and 18,489 pass attempts with participation (completion). 2022-2025 were not loaded. Walk-forward: every week is predicted by a model fit on plays dated before it.
This tests single plays. It says nothing about game margins or ATS picks.

## Headline

Knowing who is on the field improves play-level prediction slightly beyond context alone, and for completion also beyond team factors. For pressure it is **no better than team factors** (a tie within noise).
The individual effects that hold up out of sample are quarterbacks, receivers and pass rushers. Individual **offensive linemen and defensive backs do not**: their effect estimates do not repeat from one half of the data to the other.
The preregistered gate (V1, V2, V5 on pressure) passes, but V2 passes only on its weak criterion (point estimate below zero; interval includes zero), so it is a thin pass.

## Log loss per play (lower is better)

| | ctx (context only) | team | player | both |
|---|---|---|---|---|
| Pressure (base rate 32.6%) | 0.60851 | 0.60735 | 0.60687 | 0.60703 |
| Completion (base rate 64.5%) | 0.59282 | 0.59204 | 0.59096 | 0.59100 |

The combined `both` variant is slightly worse than `player` alone for pressure (+0.00016, interval +0.00005 to +0.00028) and equal for completion (+0.00004), so adding team effects on top of player effects does not help.

## Results by test

| Test | Result | Verdict |
|---|---|---|
| V1 pressure, player vs ctx | -0.00164 per play, 95% interval -0.00303 to -0.00034 | **Pass** |
| V2 pressure, player vs team | -0.00048, interval -0.00138 to +0.00041 | **Pass** on the point-estimate rule; not distinguishable from zero |
| V3 completion, player vs ctx | -0.00187, interval -0.00281 to -0.00086 | **Pass** |
| V4 completion, player vs team | -0.00108, interval -0.00188 to -0.00035 | **Pass** (interval excludes zero) |
| V5 calibration, pressure (player) | slope 0.977, intercept -0.042 (se 0.027) | **Pass** (intercept near the 0.05 limit) |
| V5 calibration, completion (player) | slope 0.965, intercept -0.002 | **Pass** |
| V6 pressure by quintile of summed OL effect, best to worst protection | 28.9%, 32.0%, 31.8%, 35.4%, 35.0%; worst minus best +6.1 points (interval +3.7 to +8.7) | **Fail**: the gap is clear but the rates are not monotone (quintile 3 below 2, quintile 5 below 4) |
| V7 split-half reliability, pressure | OL r 0.06 (120 players, interval -0.12 to 0.23); rushers r 0.32 (131, 0.16 to 0.46); QB r 0.54 (25, 0.19 to 0.77) | OL **fail**; rushers and QB pass |
| V7 split-half reliability, completion | receivers r 0.51 (34, 0.21 to 0.72); DB r 0.05 (188, -0.09 to 0.19); QB r 0.40 (37, 0.09 to 0.64) | DB **fail**; receivers and QB pass |
| V8 pregame expected lineup vs team-game pressure residual (Spearman, 544 team-games) | OL sum 0.23 (0.15 to 0.31); rush sum 0.08 (-0.005 to 0.16); OL plus rush 0.22 (0.14 to 0.29) | OL **pass**; rush **fail** (interval includes zero) |
| V8 comparisons | actual-lineup player shift 0.28 (0.20 to 0.35); team-effect shift 0.25 (0.17 to 0.33) | The pregame expected lineup (0.22) is below both the actual lineup (upper bound) and the team effect |

## What the results mean

1. The gains are real but very small: about 0.0016 to 0.0019 log loss per play against context only, roughly 0.3% of the loss.
2. A team-level pressure factor already captures nearly all of what the pressure player model finds. That is the aggregate-versus-player question the sprint was built to answer, and for pressure the answer is "no added value shown".
3. Completion is different: player effects beat team effects with an interval that excludes zero, driven by receivers and quarterbacks (their effects repeat across halves).
4. Individual linemen and defensive backs are not identifiable from who-was-on-the-field alone. Five linemen and four backs share every play and nothing says who blocked or covered whom, so the model cannot separate them. The OL unit sum still carries a gradient (V6 gap 6.1 points), which is why the unit signal works while individual OL ratings do not.
5. Those two failed repeats (OL, DB) are the part of the spec's matchup premise (individual OL vs DL, individual receiver vs defender) that public data cannot support. Assignment data would be needed.

## Limits

- One validation season. Intervals are by game clusters; per-game effects are far below detectability.
- Frozen settings came from 2020 only; the team baseline had its own best setting (half-life 365 days), the player model its own (730).
- V7 uses 2018-2019 vs 2020-2021, so its split halves are not independent of the walk-forward fits used elsewhere.
- Players with few plays are shrunk toward the position average; V7 counts only players with 400 (pressure) or 150 (completion) or more on-field dropbacks in both halves, which is why receivers and QBs number only 34 and 25-37.
- V8 uses the expected lineup from the pregame snapshot, which includes injury and snap-share limits documented in `DATA_AUDIT.md`.
