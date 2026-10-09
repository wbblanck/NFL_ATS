# Skip Filters: Pre-registration

Written before any skip rule was graded. Question: if you may skip some picks and bet only the rest, is there a rule
that wins above break-even at -110 against the closing line? All rules below are run and reported, whatever the
result. No rule is chosen from results.

## The bet

- Each model's pool pick is bet at the **closing line** (nflverse close, about 15 minutes after the lock), one unit at
  -110. A win returns 100/110 units, a loss costs 1. Pushes are refunded and left out.
- Break-even is **52.38%**. Return = (wins × 100/110 − losses) / (wins + losses).
- Only games the rule keeps are bet. Skipped games cost nothing.

## Models and windows

Each model's stale line is the proxy the pool would use (as in docs/bettable_preregistration.md). Windows are by
season.

| Model | Pick | Stale line | Discovery (stability) | Confirmation (decides) | In the Holm family |
|---|---|---|---|---|---|
| Official (live) | `patterns.dataset()` p_live > 0.5 | book open 2014-24, CBS open 2025, SBRO 2008-13 | 2008-2016 | 2017-2025 | yes |
| Key-number variant | `keynum`, SBRO open | SBRO open | 2007-2016 | 2017-2021 | yes |
| v1 (team-only) | `proj-poisson-v1`, H = 8, λ = 5, frozen | SBRO open | 2007-2016 | 2017-2021 | yes |
| Hybrid | the Hybrid rule | SBRO open | 2007-2013 | 2020-2021 only (2014-2019 were its selection years and are excluded) | yes |
| v3 (player) | `players_v3` picks, `v3_history.csv` | book open / CBS open | none | none | **no, descriptive only** (1,065 games, 2022-2025, no split) |

## Skip rules (fixed now)

Every rule uses only information known when the bet is placed (the closing line, the closing total, the schedule, and
the model's own probability). Move = |closing spread − stale spread| in points.

| ID | Keep the game when | Note |
|---|---|---|
| M1 | move > 0 | skips no-move games |
| M2 | move ≥ 1 | |
| M3 | move ≥ 2 | |
| M4 | move ≥ 3 | Max tier |
| M5 | move < 1 | Lean only |
| M6 | move < 2 | Lean and Solid |
| M7 | move < 3 | skips Max |
| P1 | model's cover probability for its pick ≥ 0.52 | official, key-number, v1 only |
| P2 | probability ≥ 0.54 | |
| P3 | probability ≥ 0.56 | |
| K1 | a 3 or 7 is crossed between the stale and closing spread | same definition as `patterns.py` |
| K2 | no 3 or 7 crossed | |
| S1 | \|stale spread\| ≤ 3 | |
| S2 | 3 < \|stale spread\| ≤ 7 | |
| S3 | \|stale spread\| > 7 | |
| U1 | the picked team is the favorite on the stale line | pick-em games are in neither U rule |
| U2 | the picked team is the underdog on the stale line | |
| T1 | closing total ≥ 45 | |
| T2 | closing total < 45 | games with no total are in neither T rule |
| W1 | week ≤ 8 | |
| W2 | week ≥ 9 | |
| D1 | division game | |
| D2 | not a division game | |
| A1 | all three of live, key-number and v1 pick the same side | frame models only (keynum, v1, hybrid) |
| A2 | not all three agree | frame models only |

Probability rules (P) are not applied to Hybrid, which has no single probability. Agreement rules (A) are not applied
to the official model, whose window is longer than the frame.

Baseline (no filter) is reported for every model and is not counted as a rule.

## Tests

For every model and rule, in each window: wins, losses, win rate, 95% Wilson interval, return, and one-sided z against
52.38%.

**Family.** Every (model, rule) pair with at least **200 confirmation bets** is in the family. Holm-corrected at 0.05
across the whole family, one-sided on the confirmation window. Pairs below 200 are reported but not counted.

**A rule is a profitable skip rule at -110** if and only if:
1. it passes Holm in its model's confirmation window, **and**
2. its discovery win rate is above 52.38% on at least 200 discovery bets.

Both conditions are required. The rule list is fixed, so discovery cannot pick winners; it is a stability check.

**Also reported, not in the family:** the same rules graded against the stale line (the pool's game, no price), as a
descriptive column; and v3 on all rules, descriptively.

## Expectation (stated before running)

- I expect **no rule passes**. The closing-line record is 50.8% for the official pick overall and 48.9% for Max, the
  weakest tier. Rules that keep only the strongest moves are therefore likely to be among the weakest, and rules that
  drop big moves are likely to sit near 51%.
- The family is large (about 90 tests), so the Holm threshold for the best rule is strict. A pass would need a
  confirmation win rate several points above break-even.

## Limits

- The models' picks overlap heavily, so Holm across models is conservative. A real edge that appears in several models
  at once would be counted several times.
- Stale lines before 2025 are proxies for the pool line, and the closing line is taken about 15 minutes after the lock.
- Flat -110 is assumed. At -105 break-even would be 51.2%. That is not tested here.
- The opposite side ("bet against the pick on some games") is a different strategy and is not in this family.
