# Generation 2 player-estimate improvement: development preregistration

Written 2026-11-11 before any model in this document is scored. **Developmental.** Data limited to seasons 2018-2020 (completion and EPA models also use 2016-2017 as training history). 2021 stays spent, 2022-2025 locked and not loaded. Nothing here is a confirmation or a claim about picks.

## Why

`LINEUP_DEV_2019_2020.md` found player estimates are mostly shrinkage and noise (lineup-score reliability about one third). Two changes target that, both fixed now with no tuning on outcomes:

1. **Informative priors** (`g2-onfield-ridge-v2-prior`): the player's prior mean depends on information known before any of his plays: draft round (1, 2, 3, 4-7, undrafted) and years of experience (0, 1, 2-3, 4+). Implemented as unpenalized group-level terms in the same regression (count of players of that bucket in that group on the field; the targeted receiver for receivers), with the player-specific deviation still ridge-penalized. A player's effect is the group-bucket term plus his deviation. Ridge strength and half-life are the frozen v1 values (100; 730 days).
2. **Richer outcome**: a second quantity per player, **EPA per pass attempt** (Gaussian ridge, same design as the completion model: targeted receiver, QB, DB and LB on the field; context air-yards bucket, pressure, down, distance, shotgun), in place of the binary completion for the coverage and passing shift. Penalty 100 on the same scale after dividing the outcome by its standard deviation, so the units compare with the logit models.

Not changed: positions, snapshots, lineup construction, walk-forward fitting, training starts (pressure 2018, completion and EPA 2016).

## What is measured (all reported, no pass rule)

| ID | Measure | Comparison |
|---|---|---|
| M1 | Walk-forward log loss on 2019 and 2020 plays, pressure and completion, paired game-cluster bootstrap | v2-prior vs v1 player model |
| M2 | Walk-forward squared error of EPA per attempt on 2019 and 2020, paired game-cluster bootstrap | EPA model vs context-only vs team-effects EPA model |
| M3 | Split-half reliability of effects by group (Pearson r with Fisher interval, same minimum plays as V7) | v1 vs v2-prior, halves 2018-2019 vs 2020 (pressure) and 2016-2018 vs 2019-2020 (completion, EPA) |
| M4 | Lineup-score reliability (variance of the score over variance plus summed squared standard errors) and share of thin slots | v1 vs v2 scores, 2019-2020 team-games |
| M5 | The same team-game regression as in the development extension (EPA per dropback on form plus lineup shift, two-way clustered by team and week, form calibrated on 2019): new combined score with the EPA-based passing shift replacing the completion shift, and each component alone | v1 vs v2 on 1,024 team-games |

Interpretation key: an improvement means higher reliability and lower play-level error, not a significant M5. M5 is reported with the same low power as before (about 1,000 team-games, effects of a few hundredths of EPA per dropback per SD). Anything that looks good here must be re-registered and scored on data not yet used before any claim.

## Guard rails

No selection among variants on these results beyond reporting all of them. No use of 2021 or later. Draft round and experience are public pre-season facts (nflverse players table); experience in a block is that season minus rookie season.
