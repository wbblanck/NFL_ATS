# Strong Calls: Pre-registration

Written before any strength tier was graded. Question: can the picks be split into strong calls and the rest in a way
that holds up out of sample, so each pick can carry an honest strength label?

## What was already settled

- `docs/mining_report.md`: an open search of 7,814 situation rules (2008-2019 search, 2020-2025 holdout) found nothing
  beyond chance; 0 of its top 25 survived. This test does **not** repeat that search.
- Known and not new: the pool win rate is higher when the market moved 1+ point (57% historically).
- Seen before this document (counts only, no outcomes): the model's cover probability is almost entirely the size of
  the move (correlation 0.96 with |move|), so "model confidence" and "move size" are one signal here.

## The tiers (fixed now, not tuned)

Move = |market close − stale line| in points, the same quantity the dashboard already shows.

| Tier | Move | Share of games |
|---|---|---|
| Lean | under 1 | 44% |
| Solid | 1 to 1.5 | 28% |
| Strong | 2 to 2.5 | 15% |
| Max | 3 or more | 12% |

## The tests

Data: the live model's pool picks, 2008-2025 (4,572 games), graded against the stale line (the pool's game). Periods:
discovery 2008-2016 (only to see direction), confirmation 2017-2025 (decides). Then the same tiers against the closing
line at -110 (the bettable game), reported only.

Hypotheses, decided on confirmation, Holm-corrected at 0.05 over the five:
1. **Strong or Max (move 2+)** wins more than 50% against the stale line (one-sided).
2. **Max (move 3+)** wins more than 50%.
3. **Trend:** win rate rises across the four tiers (logistic slope on tier 0-3, one-sided).
4. **Agreement:** where the live model, v1 and the key-number variant all pick the same side (2007-2021 SBRO frame),
   the win rate beats the games where they do not (difference, one-sided).
5. **Key-number crossing:** moves strictly through a 3 or 7 beat the rest (difference, one-sided; the rule from
   `engine/backtest/patterns.py`).

A tier counts as a **real strong call** only if its hypothesis passes Holm on the confirmation period **and** its
discovery-period win rate is also above 50%. Everything is reported either way, with 95% intervals.

2026 live (about 30 games) is shown as a descriptive holdout only.

## What a pass changes

Only the label. The pick itself never changes; a pass means the dashboard and alert may call a pick "strong" and show
the tier's historical win rate. A fail means no label is shown.

## Expectation, stated in advance

Tiers by move size will separate (the 1+ point effect is already known). Agreement and key-number crossing will not
add anything beyond move size. Nothing here will be profitable against the closing line.
