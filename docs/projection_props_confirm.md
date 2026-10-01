# Player Projection Rule for Props: Confirmation Pre-registration (2026)

Committed before any 2026 prop line or 2026 result was read (docs/projection_props_declaration.md). Code:
`engine/backtest/props_projection.py` (`run(2026)`); model `engine/models/player_proj.py`, constants fitted on
2024. Exploration output (clean data after the partial-game fix): `docs/props_projection_explore.txt`.

## What exploration showed
- The projection alone has no value: on 2024 and 2025 every under-threshold lost money (−0.7% to −7.8% in
  2025) and every over-threshold lost more; its average miss is worse than the line's (17.8 vs 16.3, 2025).
- Combined with books disagreeing, it looked useful in 2025: **P1** below, n 453, under 57.2%, ROI +5.9%
  (interval −2.6% to +15.0%). In 2024 it fired 19 times (−1.6%), too few to mean anything.

## Rule (one; tested at one-sided 2.5%)
**P1** On DraftKings' quote, bet the under when at least two real books post different lines for the prop,
DraftKings has the highest line, and that line is at least 10% above the player's pre-game projection.

## Decision
After the 2026 regular season: PASS if n >= 30 bets in >= 10 weeks and the week-clustered ROI interval
(one-sided 2.5%) has its lower end above 0. Interim looks are descriptive.
