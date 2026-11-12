# Batch 6: nfl-betting-model batch 3-5 models against the CBS pool line: Pre-registration (2026-11-08)

Requested by the owner (2026-11-08: port the later nfl-betting-model models to NFL_ATS and test them against the pool
lines). Committed before any 2026 week 10 game is played (first week 10 kickoff: Thursday 2026-11-12). Research only:
nothing here touches the pick pipeline, `predictions.csv` or the live record. Code: `scripts/batch6.py`, tests
`tests/test_batch6.py` plus the ported known-answer tests `tests/test_gamesim_{tdfg,kalman,xgb,batch5}.py`.

## What was ported (frozen, nothing refit)
| Here | From nfl-betting-model | Model | Its result there (2022-2025, 1,023 games) |
|---|---|---|---|
| `src/engine/gamesim/tdfg.py` | `src/nflbet/ats/tdfg.py` | TD/FG score model (batch 3 M1) and the pregame expected starting QB (G1) | Cover log loss vs NB better (PASS), exact margin not (FAIL); still worse than a coin flip vs the close |
| `src/engine/gamesim/kalman.py` | `src/nflbet/ats/kalman.py` | Kalman margin rating (batch 1), an XGBoost input | No gain over Elo |
| `src/engine/gamesim/xgb.py` | `src/nflbet/ats/xgb.py` | XGBoost margin model (batch 4) | FAIL: MAE 10.003 vs Elo 9.964; −9.3% ROI on 608 bets at the close |
| `src/engine/gamesim/batch5.py` | `src/nflbet/ats/batch5.py` | S1 shared-touchdown and K1 key-number margins (batch 5); R1/R2 come along unused | Both PASS on exact margin vs NB; neither beats NB on covers |
| `data/gamesim/batch1_constants.json`, `batch3_constants.json`, `batch4_model.json`, `batch5_constants.json` | `data/backtests/` same names | Frozen constants and the trained booster (fit 2016-2020; XGBoost 2016-2021) | |

Elo + QB uses the batch 1 `eloqb` constants with the G1 expected starter: the previous game's main QB unless the
final injury report lists him Out or Doubtful (nflverse injury file; injury reports from 2022 on, exactly as batch 3).
XGBoost reads the same expected starter with injury reports from 2015 on, exactly as batch 4. nflverse's injury file
holds the final pregame report, not Wednesday's.

**Key numbers:** K1 is centered on Elo's margin. This repo already tests a market-centered key-number model
(`keynum`, `docs/keynumber_preregistration.md`, failed walk-forward 2007-2021) and nfl-betting-model has a separate
market-centered test in preparation. So K1 is reported here as description only, not tested.

## Sample
- **Test: 2026 regular season, weeks 10-18**, every game with a pool line in `data/lines/league_lines.csv` (latest
  `recorded_at` per game) and a final score. No line is ever backfilled for this test.
- Run **once**, after week 18 is final, from committed code and frozen constants. Every model uses only games played
  before each forecast's week, so an after-the-fact run gives the same forecasts as a pregame run.
- Weeks 2-9 of 2026 and 2022-2025 are descriptive only.
- Spread sign: canonical. `spread` = home team's line, negative = home favored; home covers when margin > −spread;
  margin = −spread is a push and is left out.

## Tests (family of 2, Holm at 0.05, one-sided exact binomial against 50%, games as units)
- **Q Elo + expected-starter QB vs the pool line:** pick home when its fair margin > −spread, away when below; equal =
  no pick. Pass: cover count significant at its Holm level (Clopper-Pearson lower bound above 50%).
- **X XGBoost vs the pool line:** same rule with XGBoost's predicted margin.
- Holm: smaller p against 0.025, the other against 0.05, stopping at the first failure. A test with fewer than 100
  graded picks cannot pass (and Holm stops there).
- Q and batch 2's A2 (plain Elo) will mostly pick the same sides; they are separate families, so a pass in both is not
  two independent confirmations.

## Power, stated in advance
About 9 weeks × 14-15 games ≈ 130 graded picks; one pick's SD is 0.5, so the standard error is about 4.4%.
- At 0.025 a pass needs 77 of 130 (59.2%); at 0.05, 75 of 130 (57.7%). Exact power at the 0.025 level: true rate 55%
  → 19%, 58% → 42%, 60% → 61%, 64% → 89%. A fail means "no evidence", not "no edge".
- **Why TD/FG, S1 and K1 are not tested:** their sides are Elo's sides (same mean), so their only distinct claim is the
  cover probability. Their per-game SD of (ln 2 − cover log loss) against the 2022-2025 close is 0.164 (TD/FG), 0.188
  (S1), 0.222 (K1), so at 130 games the standard error is 0.014-0.019 nats. Detecting a gain over a coin flip at 80% power would take
  about 0.04 nats or more; a perfectly calibrated 55% edge gives about 0.005. A test would be close to powerless, so
  their pool-line log loss is reported with a 90% interval as description only.

## Amendment 2026-11-12: deterministic expected-starter tie-break (before any week 10 kickoff)
An audit found that the expected starter was not reproducible. When two QBs had the same dropbacks in a team's previous
game, `max(counts, key=counts.get)` took whichever came first in an unordered group-by, so Elo + QB and XGBoost moved from run
to run (XGBoost MAE over a range of 0.0053, Elo + QB 0.0023, against the 0.0006 gate). A re-run on 2026-11-09 passed 9 of 11
checks; the "all eleven within rounding" result below was one draw of that tie. The injury-report start years do not explain
the first miss (moving Elo + QB's injury start from 2022 to 2015 changes its MAE by 0.0001); this was the tie.
- Rule now: most dropbacks, ties to the smallest QB id (`tdfg.top_qb`), and `qb_games` is sorted by (day, game_id, qb). No
  constant, model or test rule changes. About 0.16% of team-games have a tie and none of 2026 so far, so a week 10-18 pick is
  expected to be affected in at most one game.
- The rule was chosen before its numbers were looked at. It gives Elo + QB 9.92322 and XGBoost 10.00478 on the 1,023 games
  (the other nine numbers are unchanged). `scripts/batch6.py reproduce` now checks those two against the registered 9.921 and
  10.003 within 0.006 (the spread across tie resolutions) and against the pinned values within 0.00002, which makes it a
  determinism check. Two consecutive runs gave identical values.
- Nothing else in this pre-registration changes: same test weeks, line, model set, Holm family and minimum picks.

## Known answers first (done before this commit)
1. `scripts/batch6.py reproduce` reproduces all eleven registered 2022-2025 numbers within rounding
   (`data/gamesim/batch6_reproduce.json`): 1,023 games; MAE Elo 9.964, Elo + QB (expected) 9.921, XGBoost 10.003;
   cover log loss vs the close NB 0.7129, TD/FG 0.7077, S1 0.7117, K1 0.7168; share of margins on 3: TD/FG 5.6%,
   S1 6.4%, K1 14.3%. The first run missed Elo + QB and XGBoost by about 0.002 points: the injury-report start years
   above (2022, 2015) had not been copied. Fixed before anything else ran.
2. Cover probability hand cases: a certain 4-point home win covers −3.5; at −3 pushes are removed; at +2.5 a 50/50
   between −2 and −4 gives 0.5.
3. Synthetic log loss: a planted calibrated signal over 2,000 games is found; with a coin-flip outcome and noisy
   forecasts over 130 games the bootstrap claims a gain in at most 5% of 200 seasons.
4. Holm and the 100-pick minimum: hand cases in `tests/test_batch6.py`. The exact binomial and grading reuse batch 2's
   functions and checks.
5. The ported model tests (`tests/test_gamesim_tdfg.py`, `_kalman.py`, `_xgb.py`, `_batch5.py`) pass with only their import paths changed.

## Descriptive only
Weeks 2-9 and 10-18 of 2026: every model's record against the pool line and margin MAE (Elo, Elo + QB, XGBoost), the
pool line's MAE, cover log loss and side record of NB, TD/FG, S1 and K1, and agreement with the official pick.
