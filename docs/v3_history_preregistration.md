# v3 History: Pre-registration

Written before v3's per-game picks were graded against any line. Purpose: give the player projection (v3) a
historical bettable record like the other models (docs/bettable_report.md), so it can be judged on more than 30 live
games.

## What is rebuilt

- The pipeline in `engine/backtest/players_v3_eval.py`, unchanged: train-only constants, (D, k) tuned on 2013-2021, β
  fit on 2013-2021 and frozen, point-in-time features. Test A is 2022-2024, Test B is 2025.
- v3 is **not** refit year by year. A walk-forward version would be a different model and is not tested here.
- Per game: v3's and v1's cover probability against the stale line (book open 2022-2024, CBS open 2025). The pick is
  the side with probability above 0.5, as for every other model.
- Games: those in both v3's scored set and the live backtest set (`patterns.dataset()`), so v3, v1 and the live
  model are compared on identical games.

## Reproduction check (before anything is graded)

The rebuild must match the published run (`data/backtests/players_v3.json`): 815 scored games in Test A and 272 in
Test B, and the half-point-open 2025 records (v3 104-106, v1 107-103). If any of these differs, the result is
reported as "does not reproduce" and no profitability claim is made.

## The test

- Same bet as docs/bettable_preregistration.md: the pool pick, bet at the closing line, one unit at -110, break-even
  52.38%, pushes refunded.
- v3 joins that document's Holm family, making it five models. v3 is profitable only if its one-sided z against
  break-even clears Holm at 0.05 across the five (the best of five needs p <= 0.01).
- Reported for every model on the same games: record against the stale line and against the closing line, by period
  (2022-2024, 2025), with 95% intervals.

## Limits

- About 1,000 games: a true 54% bettor would clear the bar only about two times in five. This test can show v3 is
  clearly bad; it cannot show a small real edge.
- Stale lines are proxies for the pool line, as everywhere in this project.
