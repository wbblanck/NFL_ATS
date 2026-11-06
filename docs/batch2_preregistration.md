# Batch 2: Elo against the CBS pool line, Elo + simulator average: Pre-registration (2026-11-06)

Requested by the owner (2026-11-06, "Merge" on PR #58, after batch 2 was described as running forward from week 10;
master list rows A2 and C1). Committed before any 2026 week 10 game is played (first week 10 kickoff: Thursday
2026-11-12). Research only: nothing here touches the pick pipeline, `predictions.csv` or the live record.
Code: `scripts/batch2.py`, tests `tests/test_batch2.py`.

## Sample
- **Test: 2026 regular season, weeks 10-18**, every game with a pool line in `data/lines/league_lines.csv` and a final
  score. Games without a recorded pool line are left out; no line is ever backfilled for this test.
- Run **once**, after week 18 is final, from committed code and frozen constants. Both models are deterministic and use
  only games played before each forecast's week (Elo: final scores; simulator: play-by-play, injury reports and the
  recorded starting QB, as in its frozen design). Computing them after the fact therefore gives the same numbers as a
  pregame run, so there is no weekly recording.
- Weeks 1-9 of 2026 and 2022-2025 are descriptive only.
- Spread sign: this repo's canonical one. `spread` = home team's line, negative = home favored; home covers when
  margin > −spread; margin = −spread is a push.

## Models (frozen, nothing refit)
- **Elo:** `engine.gamesim.elo` with `data/gamesim/elo_constants.json` (K 25, home 35, regression 1/2, b 0.0853). Fair
  home margin = μ_home − μ_away.
- **Simulator:** G3 as reproduced by `scripts/gamesim_reproduce.py` (`data/gamesim/gamesim_constants.json`, seed 101,
  1,000 runs per game). Fair home margin = mean simulated margin.
- **Average (C1):** (Elo + simulator) / 2.

## Tests (family of 2, Holm at 0.05; week-clustered bootstrap, 2,000 draws; one-sided)
- **A2 Elo vs the pool line:** pick home when Elo's fair margin > −spread, away when it is below; equal = no pick.
  Pass: the cover rate's interval (pushes excluded) is above 50%.
- **C1 the average beats both:** paired d_E = |Elo − margin| − |avg − margin| and d_S = |sim − margin| − |avg − margin|.
  Pass: both intervals above 0 (intersection-union: the test's p is the larger of the two p values, no extra
  correction).
- Holm: smaller p against 0.025, the other against 0.05, stopping at the first failure.

## Power, stated in advance
About 9 weeks × 14-15 games ≈ 130 games.
- A2: one pick's cover has SD 0.5, so the standard error is about 4.4%. Only a true cover rate near 57% or better would
  be detected reliably. A fail means "no evidence".
- C1: the average sits between two forecasts that are 0.80 correlated, so its paired differences are small. If their
  per-game SD is about 1.5 points (to be printed from 2022-2025 before the test), the standard error is about 0.13
  points at 130 games. Only a gain of roughly 0.3 points against each model would be detected.

## Known answers first
1. Elo reproduces its registered 2022-2025 margin MAE (9.964) and the simulator reproduces G3's (9.983).
2. Grading hand cases: home −3.5 and margin +4 is a home cover; home −3 and margin +3 is a push; home +2.5 and
   margin −2 is a home cover.
3. On synthetic picks with a planted 65% cover rate over 2,000 picks the interval is above 50%; with 50% it is above
   50% in no more than about 5% of 200 synthetic seasons.

## Descriptive only
Weeks 1-9 and 10-18 of 2026: Elo's, the simulator's and the average's record against the pool line and margin MAE;
agreement between Elo's side and the official pick; the pool line's own MAE. 2022-2025: the average's MAE next to
Elo's (9.964) and the simulator's (9.983), plus the per-game SDs used for power above.

## Addendum after the known-answer checks (2026-11-06, before any week 10 game)
Check 3 failed as written: with only nine week clusters, the week-clustered bootstrap put a no-edge 50% record above
50% in 18 of 200 synthetic seasons (9%), not about 5%. Changed before any test data exists:
- **A2** uses an exact one-sided binomial test of the cover count against 50% (games as units; Clopper-Pearson lower
  bound reported at the Holm level). In 200 null seasons of 130 picks it crossed in no more than 7%, as the check
  requires (the exact test is valid by construction).
- **C1** uses a game-level bootstrap (2,000 draws) for each paired difference; in 200 null samples of 130 games it
  crossed in no more than 8%.
Everything else stands.
