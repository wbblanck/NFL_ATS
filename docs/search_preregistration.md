# Brute-Force Setting Search: Pre-registration

Committed before any setting was scored. Idea: try roughly a thousand combinations of the model's own settings,
keep the best, and check it on data the search never saw. The protocol below is what makes that check honest.

## Data (same as the adaptive and pattern tests)

2008–2025 regular season; stale line = SBRO open 2008–2013, book open 2014–2024, CBS open 2025; market = nflverse
close and total. Pushes excluded.

## Settings searched (every combination)

- **Margin distribution:** `shifted_total` (live), `shifted`, `normal_total`, `keynum`.
- **Training window:** all earlier seasons, the last 10, the last 5.
- **Blend weight w** between the market-move cover chance and the team-only projection's cover chance
  (proj-poisson-v1): w in {0, 0.1, 0.2, 0.3, 0.5}. v1 settings (half-life H in {4, 8, 16} games, ridge lambda in
  {2.5, 5, 10}) apply when w > 0.
- **Blend only where the market moved little:** the projection enters only when the move off the stale line is below
  d in {0.5, 1, 1.5, all} points (above d: the market cover chance alone).
- Pick = the side with the higher blended cover chance. About 1,000 settings; the live model is one of them
  (shifted_total, all seasons, w = 0).

## Three stages, each on seasons the earlier stage did not use for choosing

1. **Search 2008–2015:** score every setting by log loss on all games; keep the best 20.
2. **Validate 2016–2019:** among those 20, pick the one with the lowest log loss.
3. **Test 2020–2024 (half-point book opens) and 2025 (CBS opens):** score that one setting once.

## Decision

Pass only if the chosen setting beats the live model on the test seasons on games where their picks differ
(one-sided z >= 1.645), has lower log loss, and is not behind the live model on 2025. Reported either way:
- how each setting's validation rank carries over to the test (rank correlation across all settings),
- the best-of-1,000 shortfall: the gap between the winning setting's search-period result and its test result,
- the same three-stage run on 20 simulated histories drawn from the live model's own probabilities (no real
  pattern exists), to show how good a "best of 1,000" looks by chance.

A pass would go to a separate pre-registered live-tracking rule; nothing here changes the pick.
