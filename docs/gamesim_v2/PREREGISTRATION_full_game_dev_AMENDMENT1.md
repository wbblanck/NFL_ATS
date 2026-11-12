# Amendment 1 to PREREGISTRATION_full_game_dev.md (before any margin is scored)

Written 2026-11-12 after the ratings stage ran and before any game margin was looked at.

## Why

The preregistration fixed the ridge strength at 100, carried over from the logistic pressure and completion models. The required play-level check shows that on the EPA scale, with all 22 players in the design, this penalty overfits: walk-forward squared error versus context only is worse for dropbacks by +0.032 (interval +0.024 to +0.039, 57,475 plays, 2019-2021) and for runs by +0.009 (+0.006 to +0.012, 37,091 plays). Ratings that predict plays worse than no ratings would make the margin test a test of a mis-set penalty rather than of the idea.

## Change

- The ridge strength (one value for all player groups, separately for dropbacks and runs) is chosen from {100, 300, 1,000, 3,000, 10,000, 30,000} by walk-forward play-level squared error on **2018 only** (training from 2016, same decay). 2019-2021 play results are not used for the choice.
- The chosen values define the **primary** test. Everything else in the preregistration (lineup shift, games, pass rule, reported items) is unchanged.
- The original ridge-100 version is run and reported as a secondary result, so both are visible.

## Disclosure

The decision to amend was triggered by the 2019-2021 play-level check (listed in the preregistration as a reported item). No game margin, closing-line comparison or team-form comparison had been computed when this was written.
