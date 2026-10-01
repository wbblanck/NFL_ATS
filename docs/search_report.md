# Brute-Force Setting Search: Report

Rules: `docs/search_preregistration.md` (committed before any setting was scored). Numbers:
`data/backtests/search.json`; code `engine/backtest/search.py`. **1,740 settings** (4 distributions × 3 training
windows × [live baseline + 4 blend weights × 3 half-lives × 3 ridge values × 4 move limits]), searched on 2008–2015,
validated on 2016–2019, tested once on 2020–2024 (half-point book opens) and 2025 (CBS opens).

## Result: fail

The best setting after the three stages: `shifted_total`, last 10 seasons, 10% team-only projection blended in
(half-life 4, ridge 10), only where the market moved less than ½ point.

| | Chosen setting | Live model |
|---|---|---|
| Search 2008–15 log loss | 0.68748 | 0.68724 |
| Validation 2016–19 log loss | 0.68748 | 0.68782 |
| **Test 2020–24, half-point opens** | 395-310 | 394-311 |
| Games where the picks differ | 5: won 3 / 2 (z = 0.45) | |
| Test log loss | 0.68288 | 0.68263 |
| 2025 CBS opens | 109-101 | 108-102 |

The chosen setting makes the same pick as the live model in 700 of 705 test games, and its probabilities are
marginally less accurate (0.68288 vs 0.68263). It fails the pre-registered rules (z < 1.645, higher log loss).

## What the search shows

- **Almost no setting beats the live model reliably:** of 1,740, 88 beat it on validation log loss and 244 on the
  test, but only **2** beat it on both.
- **The search period already preferred the live model:** the best of 1,740 on 2008–15 (0.68748) was *worse* than the
  live model's own setting (0.68724): the live configuration is at or near the optimum of this whole space.
- **Rankings carry over (Spearman 0.77 between validation and test across settings)**, but because most settings are
  near-copies of each other, not because they are good: the structure of the space (which distribution, how much
  blending) matters more than fine-tuning.
- **Luck check:** the same three-stage search on 20 histories simulated from the live model's own probabilities
  (no real pattern) gave a test z with median −0.25 and a 95th percentile of 2.04, and up to +2.83 in one history:
  a best-of-1,740 can look significant by chance. The real run's z of 0.45 is ordinary.

## Conclusion

Tuning the model's own settings, blending in the projection, and changing the distribution or training window does not
improve the picks. The live model's settings sit at the optimum of what we can search; further gains would have to
come from new information, not from re-tuning. The live model is unchanged.
