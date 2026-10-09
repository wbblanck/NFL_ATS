# Bettable Record: Report

Rules: `docs/bettable_preregistration.md` (committed before the new tests, `cbb1279`). Numbers:
`data/backtests/bettable.json`; code `engine/backtest/bettable.py` (`python -m engine bettable`).

## Result: no model cleared break-even

Each model's pool pick, bet at the closing line, one unit at -110 (break-even 52.38%). Decision z is one-sided
against break-even, Holm-corrected over the four models.

| Model | Decision window | Bets | Win rate (95%) | Return | z vs break-even | Profitable? |
|---|---|---|---|---|---|---|
| Live (official) | 2008-2025 | 4,479 | 50.8% (49.4-52.3) | -3.0% | -2.10 | no |
| Key-number variant | 2007-2021 | 3,655 | 51.3% (49.7-52.9) | -2.0% | -1.28 | no |
| v1 (team-only projection) | 2007-2021 | 3,655 | 49.7% (48.0-51.3) | -5.2% | -3.30 | no |
| Hybrid | 2007-2013 + 2020-2021 | 2,202 | 52.2% (50.1-54.3) | -0.4% | -0.19 | no |

v3 has no backtest here (its historical per-game picks are not stored); it is judged by live tracking only.

## The same picks against the stale line (the pool's game)

| Model | Against the stale line | Against the closing line |
|---|---|---|
| Live | 54.6% (2,495-2,077) | 50.8% (2,276-2,203) |
| Key-number variant | 54.6% | 51.3% |
| v1 | 50.8% | 49.7% |
| Hybrid (all 2007-2021) | 54.5% | 51.1% |

Every model except v1 beats the stale line by about four points and none beats the closing line. The edge is the
information in the market's move that the stale number lacks. It is real for the pool, and it is not available to a
sportsbook bettor, who is quoted the moved line.

## By period (win rate against the closing line)

| Model | 2007-2013 | 2014-2019 | 2020-2021 |
|---|---|---|---|
| Key-number variant | 52.6% | 50.2% | 50.3% |
| v1 | 51.2% | 48.6% | 47.5% |
| Hybrid | 52.5% | 49.4% | 51.1% |
| Live, 2008-2013 / 2014-2024 / 2025 | 53.0% | 50.0% | 47.0% |

Every model was a little better in the early seasons and weaker after 2014. The reason is a guess, not tested: the
SBRO opens used before 2014 may be a staler proxy than the book opens used after, which would flatter the early years.

## What it shows

- **No model is profitable at -110.** The live model, the key-number variant and v1 are each below break-even; the live
  model and v1 are below it by more than two standard errors.
- **Hybrid is the closest, and still not there.** Outside the seasons it was chosen on, it won 52.2% (1,149-1,053),
  above a coin flip (z = +2.07 against 50%) but below the 52.38% that -110 requires (return -0.4%). Its 2014-2019
  stretch, the one it was chosen on, was 49.4%.
- **The pool is the game these models win.** Against the frozen line the live model has won 54.6% over 4,572 games.

## Limits (as pre-registered)

- Flat -110. At -105 the break-even is 51.2%, which Hybrid's decision window (52.2%) would clear, but the pool is
  not graded at any price and a book is rarely at -105 on both sides. Not tested.
- "Closing" is a little after the lock. Stale lines before 2025 are proxies for the pool line.
- Only one definition of a bet: the pool pick taken at the close. A bettor comparing each model's own projection with
  the closing line would make different bets (not tested).
- The live model's result was seen before the registration (disclosed there); the other three were not.
