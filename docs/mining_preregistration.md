# Open Pattern Search: Pre-registration

Committed before any search was run. The patterns are not chosen in advance; the **procedure** is. The 15
candidates in docs/patterns_report.md were already seen (their conditions reappear here as part of the grid).

## Data split

- **Search set: 2008–2019** regular season (stale line: SBRO open 2008–2013, book open 2014–2019). The search
  looks only at these seasons.
- **Holdout: 2020–2025** (book open 2020–2024, CBS open 2025), never looked at during the search. (2020–2024 were
  the confirmation seasons of earlier tests, but never searched for these rules.)
- **Forward:** 2026 live season.
Market = nflverse close and total; cover probability = the live model (fit on earlier seasons); pushes excluded.

## What a "pattern" is

A rule "in situation C, take side S", scored by how much S beats the live model's own cover probability for S:
z = (wins − sum of predicted probabilities) / sqrt(sum p(1 − p)).

- **Sides:** home, away, favorite, underdog, the side the market moved toward, the side it moved away from.
- **Situations (all known before kickoff):** week bucket, month, weekday / primetime, neutral site, division game,
  roof, surface, cold (< 40 °F), wind (≥ 15 mph), spread-size bucket, total bucket (season terciles of past
  seasons), move size and direction (toward favorite / underdog, 0, ½, 1, 1½–2½, 3+), move crossing 3 or 7,
  rest difference and byes, time zones travelled by the away team, each team's previous result (big win/loss,
  covered or not), 3-game cover and win streaks, records after week 4; each situation alone and every pair of
  them; plus team, head coach and referee alone (each with every side).
- Minimum 60 search-set games per rule.

## Luck check

The same search run on 50 simulated histories where outcomes are drawn from the live model's own probabilities
(so no real pattern exists). This gives how many rules, and how strong, luck alone produces from a search this
size. If the real search's top results do not exceed the simulated ones, the search found nothing.

## Holdout test (decides)

The 25 strongest search-set rules (by z) are tested on 2020–2025 in their search direction, one-sided,
Holm-corrected over 25 at 0.05. A survivor is then checked for whether it changes any pick (S disagrees with the
live pick inside C and wins more than half). Nothing changes the live pick without a separate pre-registered live
test and the user's approval.
