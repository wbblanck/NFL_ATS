# Skip Filters: Report

Rules: `docs/skip_filters_preregistration.md` (committed `5b66988`, before any rule was graded). Code and tests:
`engine/backtest/skip_filters.py`, `tests/test_skip_filters.py` (committed `294c6f1`, before the run). Numbers:
`data/backtests/skip_filters.csv` (every row, 123 in all) and `data/backtests/skip_filters.json`. Run with
`python -m engine skip-filters`.

## Result: no skip rule is profitable at -110

- **86 tests counted** (95 registered model-rule combinations, minus 9 with fewer than 200 confirmation bets).
  Holm threshold for the best test: p ≤ 0.00058, about z = 3.2 one-sided. The best test has z = 0.80 (p = 0.21).
  **Tests passing Holm: 0. Skip rules that are real: none.**
- The no-filter baselines reproduce `data/backtests/bettable.json` exactly for all four models, so the bets and games
  are the same as the earlier closing-line record.
- v3 (2022-2025, 1,039 picks) was run on every rule descriptively. It has no discovery split and is not in the family.

## Best rule per model (the one with the highest confirmation z)

| Model | Baseline, all / confirmation | Best rule | Discovery | Confirmation | p (raw) | Holm |
|---|---|---|---|---|---|---|
| Official (2008-25; confirm 2017-25) | 50.8% / 50.3% | K1, a 3 or 7 crossed | 51.6% (128) | 54.0% (239) | 0.31 | no |
| Key-number variant (2007-21; confirm 2017-21) | 51.3% / 50.6% | S2, spread 3 to 7 | 52.7% (940) | 53.4% (487) | 0.33 | no |
| v1 (2007-21; confirm 2017-21) | 49.7% / 48.9% | S3, spread over 7 | 50.0% (580) | 53.5% (288) | 0.36 | no |
| Hybrid (2007-13 + 2020-21) | 52.2% / 51.1% | M7, skip Max | 52.4% (1,540) | 54.5% (369) | 0.21 | no |

Discovery figures are in brackets as bets counted. Confirmation for Hybrid is 2020-2021 only, because 2014-2019 were its
selection years.

## Near misses: above break-even in both halves, not significant

Three rules were above 52.38% in both halves, on at least 200 discovery bets. None passes the correction:

- **Hybrid, skip Max (M7).** Over all 1,909 bets it wins 52.8% (ROI +0.8%). Discovery is 52.4% on 1,540 bets, an ROI of
  about zero. Confirmation is 54.5% on 369 bets (+4.0%). Raw p = 0.21, and Holm needs 0.0006. This is the closest thing
  to a skip rule in the data. It is a lead to watch, not a finding.
- **Key-number variant, spread 3 to 7 (S2).** 52.7% on 940 discovery bets, 53.4% on 487 confirmation bets (p = 0.33).
- **Hybrid, underdog (U2).** 52.7% on 967 discovery bets, 53.5% on 258 confirmation bets (p = 0.36).

## Is that more than chance?

The highest raw confirmation rate across the 86 tests is 54.5%. I checked this against a null in which every rule's true
win rate equals its own model's baseline, with the same bet counts:

- the best of 86 in a null trial has median **56.6%** (95th percentile 59.7%);
- the observed best of 54.5% is below that median. In 96% of null trials the best is at least as high.

So the best results are not distinguishable from noise across 86 rules of this size.

## What this means for skipping

1. **No subset of these picks beats -110.** The official pick wins 50.8% overall at the close, and no skip rule moves it
   above break-even in both halves on a useful sample. Official K1 (key numbers crossed) wins 53.1% over 367 bets, but
   the halves disagree: 51.6% in discovery, 54.0% in confirmation.
2. **A 2-point edge cannot be confirmed in practice with this data.** Confirming a true 54% rule at 80% power takes about
   5,900 bets. The Hybrid skip-Max rule bets about 210 games a season, so that is roughly 28 seasons.
3. **The key-number effect is in the stale line, not the closing line.** Official K1 wins 66.5% against the stale line
   (the pool's game) but 54.0% at the close. The market has absorbed most of it, which matches the earlier results.
4. **In a pool, skipping only helps if your scoring rewards win percentage.** Against the stale line, the lowest rate of any
   official rule in confirmation is 51.9% (Lean only), so every subset is above 50%. If a skipped pick scores nothing and
   the pool counts correct picks, skipping can only lower your total. If it scores by win percentage, skipping Lean
   picks (move of at least 1) raises the rate from 54.8% to 57.1%, but you give up about 43% of picks. That is a
   change in the pool's own score, not an edge against the line. **How your pool scores a skipped game is unknown to me**,
   and it decides which of these applies.

## Not tested

- **Betting the opposite side** on some games ("fading" a rule). That is a different strategy and needs its own
  registration.
- **Your pool's exact scoring of skipped games.** See point 4 above.
- **Prices other than -110.** At -105 break-even is 51.2%, which would change Hybrid skip-Max's margin. Not tested here.
- **A discovery/confirmation split for v3.** Its history is 2022-2025 only.

## Limits

- The models' picks overlap heavily, so Holm across models is conservative.
- Stale lines before 2025 are proxies for the pool line, and the closing line is taken about 15 minutes after the lock.
- Hybrid's confirmation is two seasons, so its tests are thin, and the rule was chosen partly on 2014-2019.
