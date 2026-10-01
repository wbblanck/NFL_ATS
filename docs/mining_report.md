# Open Pattern Search: Report

Rules: `docs/mining_preregistration.md` (committed before the search). Numbers: `data/backtests/mining.json`;
code `engine/backtest/mining.py`. 2,220 situations × 6 sides = 7,814 rules with at least 60 search-set games.
Search 2008–2019 (2,992 games), holdout 2020–2025 (1,580 games).

## Luck check: the search found no more than luck produces

| | Real search | 50 simulated histories with no real pattern (median / 95th percentile) |
|---|---|---|
| Strongest rule (z) | 4.33 | 3.67 / 4.22 |
| Rules with z > 3 | 8 | 9 / 25 |
| Rules with z > 2 | 155 | 175 / 221 |
| 25th-strongest rule (z) | 2.65 | 2.70 / 3.01 |

A search this size produces dozens of impressive-looking rules from pure chance. The real data produced the same
number, of the same strength.

## Holdout: none of the top 25 survives

| Top search-set rules (examples) | Search 2008–19 | Holdout 2020–25 |
|---|---|---|
| Home failed to cover last week & away lost by 14+ last week → against the move | 110/181 (z 4.33) | 41/99 (z −0.41) |
| Referee Brad Allen → against the move | 48/70 (z 3.98) | 38/75 (z +1.26) |
| Weeks 13–16 & away team 2/3+ wins → move side | 103/150 (z 3.52) | 42/78 (z −0.29) |
| Weeks 1–4 division game → underdog | 146/240 (z 3.03) | 50/109 (z −1.04) |
| Weeks 13–16 & home covered 3 straight → underdog | 57/85 (z 2.84) | 12/41 (z −2.89) |
| Spread exactly 3 → move side | 180/282 (z 3.03) | 78/126 (z +1.28) |

0 of 25 pass (best holdout p = 0.10 against a required 0.002). Most rules fall back to the model's own rate or
reverse. The only consistent thread is moves around a spread of 3 (holdout z +1.28, not significant), which is
the key-number calibration effect already found in docs/patterns_report.md and does not change picks.

## Conclusion

Searching every situation, pair of situations, team, coach and referee finds nothing beyond chance against the
live model. The market move after the pool line is set remains the only signal. The live model is unchanged.
