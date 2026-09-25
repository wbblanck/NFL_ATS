# Key-Number Fix: Report

The rules were pre-registered in `docs/keynumber_preregistration.md` before any
result.

## The candidate

`keynum` is a discrete normal centered on the market, with key-number weights
learned from past games only. It reproduces the real spikes: **8.5% of games
on 3 and 5.7% on 7**, against 8.7% and 5.9% in real games. The current
estimator gives 3.5% and 2.7%.

## Primary test (decides): walk-forward 2007–2021, 3,722 games — **FAIL**

| Estimator | Log loss | ATS | Lines 2.5/3.5/6.5/7.5 only |
|---|---|---|---|
| **shifted (live)** | **0.6862** | **54.89%** (2043-1679) | 54.1% (452-384) |
| keynum | 0.6879 | 54.57% (2031-1691) | 55.6% (465-371) |

The two estimators disagreed on 746 picks. `keynum` gained 13 games next to 3
and 7 but lost more elsewhere. The likely cause is that it tilts toward the
favorite when the market has not moved: with market and league line both at
−2.5, it gives the home side 52.4%. **Per the pre-registered rule, the live
estimator stays `shifted`.**

## Confirmation seasons (reported, cannot overturn)

- **2023, 2024:** the CBS week pages for these seasons no longer show opening
  lines (0 games), so no test was possible.
- **2025:** the CBS open is the frozen line and the distribution was trained
  on 1999–2024.

  | Games | shifted | keynum |
  |---|---|---|
  | Half-point opens (210) | 108-102, 51.4% | **121-89, 57.6%** |
  | All games with an open (267) | 130-137 | **144-123** |

  They disagreed on 76 games, and `keynum` won 45 of them.

## Reading it

Fifteen seasons say `keynum` is slightly worse. One season says it is clearly
better. Switching on the strength of the one season that happens to look good
would be cherry-picking, which the rules were written to prevent. The 2025
gap (+14 wins) is also within what one season's noise can produce.

## What happens now: a live head-to-head

- **Every live pick now records `keynum`'s probability and pick** as
  `shadow_p_home_keynum` and `shadow_pick_keynum` in
  `data/predictions/predictions.csv`. `python -m engine grade` reports the
  shadow record and its record on the games where the two disagree. The
  shadow never makes the pick.
- **Switch rule, pre-registered now:** at the end of the 2026 regular
  season, switch the live estimator to `keynum` only if, on the games where
  the two disagree, `keynum`'s win share has a one-sided z ≥ 1.645 against
  50%.
- The same rule will be applied to the 2027 season if 2026 is inconclusive.
