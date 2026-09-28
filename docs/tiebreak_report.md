# EPA/Efficiency Tie-Breaker in No-Move Games: Report (failed)

- **Rules:** `docs/tiebreak_preregistration.md` (commit `ce4dd6f`), committed before any subgroup result.
- **Code:** `src/engine/backtest/tiebreak.py`.
- **Numbers:** `data/backtests/tiebreak.json`.

## Result: **fails.** The live model is unchanged.

| No-move games, 2010–2021 (539) | ATS | Win rate |
|---|---|---|
| EPA tie-breaker | 278–261 | 51.6% ± 2.2 |
| Live model | 276–263 | 51.2% ± 2.2 |

- **The picks differ in 250 of the 539 games.** In those, the tie-breaker was right 126 times and the live model
  124 times.
- **Paired z = 0.13.** The rule needed ≥ 1.96.
- **Both are coin flips.** In games where the market doesn't move, neither line movement nor EPA picks the winner
  against the spread.

## Diagnostics (not decisive)

| Subset | Tie-breaker | Live | Games where picks differ (tie-breaker only / live only) | z |
|---|---|---|---|---|
| ½-point-move games, 2010–2021 (702) | 52.4% (368–334) | 51.1% (359–343) | 351 (180 / 171) | 0.48 |
| 2025, CBS half-point opens with no move (66) | 36–30 | 36–30 | 32 (16 / 16) | 0.00 |

- **The fitted weights change sign across seasons.** For example, success rate goes from +7.7 points per unit in
  2010 to −5.7 in 2019.
- This is the same pattern seen in the all-games test: the differentials do not predict the market's error.
- **Conclusion:** this is the fourth test of EPA/efficiency against the market, and all four have come back null.
  No further EPA variants are planned unless new data appears, such as point-in-time information the market
  would not have at lock.
