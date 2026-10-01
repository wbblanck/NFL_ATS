# Weekly Tiebreaker (Total Points in the Last Game): Report

The pool breaks weekly ties by the closest guess of total points in the week's last game. Code
`engine/picks/tiebreak_total.py`; shown in the dashboard's Tiebreaker panel.

## Which number to enter

Closest guess wins, so the best single guess is the one with the smallest expected miss: the **median** of the
final total. The market total (nflverse consensus `total_line`) is our estimate of that median.

| 2010–2025 regular season | Games | Actual − market, median | Mean | Average miss using the market | Using one fixed number |
|---|---|---|---|---|---|
| All games | 4,223 | 0.0 | +0.5 | 10.5 | 11.0 |
| Week's last game | 280 | −1.5 | −1.0 | 10.1 | 10.5 |
| Last game, 2018–2025 | 141 | −1.5 | | 9.9 | |

Typical range around the market total (all games): half land within −8.5 to +9, 8 in 10 within −15.5 to +18.

## Can we beat the market total?

- **Shrinking toward the league average total plus a shift**, fitted on 2010–2017 and tested on 2018–2025:
  - All games: 10.407 vs 10.403 for the market total, so no gain.
  - Last games: 9.77 vs 9.88. That is a 0.11-point gain, and the bootstrap gives a 95% interval of −0.11 to +0.35 (P ≈ 0.17). Not significant.
- **Night games** have finished slightly under the total since 2018 (442 games, median −1.5). In 2010–2017 they went the other way (median +0.5), so this is not a stable effect.
- **Team projections** score games less accurately than the market for totals as well as spreads (docs/total_report.md and the projection reports). They are not used.

## Rule

- Guess = the market total rounded to a whole number, with .5 rounded down.
  - Rounding down moves the guess half a point in the direction of the recent night-game lean. Over the held-out years both rounding directions miss by about the same.
- The miss averages about 10 points, so the tiebreaker is mostly luck.
- Enter the guess as late as the pool allows, using the market total at that time.
  - The dashboard reads nflverse's total, which updates through the week. Our odds captures pull spreads only, to save API credits.

## 2026 so far

| Week | Game | Total | Guess | Final | Miss |
|---|---|---|---|---|---|
| 1 | DEN @ KC | 42.5 | 42 | 41 | 1 |
| 2 | NYG @ LA | 47.5 | 47 | 34 | 13 |
| 3 | PHI @ CHI | 42.5 | 42 | 34 | 8 |
| 4 | ATL @ NO | 47.5 | 47 | | |

The totals shown are nflverse's closing totals for weeks 1–3, not totals captured at entry time.
