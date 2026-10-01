# Picking Winners (Straight Up): Pre-registration

Committed before any result below. Already seen (disclosed): the market favorite's win rate by season and by spread
size, 2010–2025 (66.5% overall; 53% when favored by 2.5 or less), and v3's win-probability log loss on 2022–2025
(docs/players_v3_report.md: 0.620 vs the market's 0.610).

## Pickers

- **Market:** the team the closing spread favors. Win probability = P(margin > 0) from the live margin distribution
  (`shifted_total`, fit on seasons before each season) given the closing spread and total; a pick'em goes to the
  side with the higher probability.
- **v1** (proj-poisson-v1, live settings, refit before each week): the team with the higher projected points.
- **v3** (proj-players-v3, frozen model): same, 2022–2024 only (the seasons with rebuilt v3 inputs).

## Test (the only place a gain is plausible): close games

- Games whose closing spread is 2.5 points or less, regular season, ties excluded.
- **Primary:** v1 vs Market on 2010–2025 close games: on games where the picks differ, v1 must win more with
  one-sided z >= 1.645. Secondary (reported): v3 vs Market on 2022–2024 close games; both pickers on all games.
- A pass would add the projection as the straight-up pick for close games **in the tracker only**; it never affects
  the ATS pick. A fail keeps Market as the tracked straight-up pick.

## Tracker (built regardless of the result)

Straight-up record per week for Market, v1 and v3, with the **expected** wins (sum of Market's win probabilities)
so a chalky season is not mistaken for skill. Live weeks use the market and projections recorded at lock; weeks
without live rows (2026 weeks 1–2 and ATL@GB) are back-filled from the closing line and point-in-time projections
and marked as backtest.
