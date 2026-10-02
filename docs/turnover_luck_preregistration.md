# Turnover and Late-Score Luck: Pre-registration

Committed before any result was computed. Idea: turnover margin, fumble recoveries, close-game results and late
cover swings are mostly luck. If the market over-reacts to a team's lucky (or unlucky) recent results, fading them
should beat the live model the following week.

Context, disclosed: the idea came from reviewing the six 2026 week 3 losses, several of which were decided by
turnovers or late scores. 2026 games are not used below. I expect a fail: the market has priced these ideas for
years.

## Data and scoring (identical to docs/patterns_preregistration.md)

- 2008–2025 regular season.
- **Stale line:** SBRO open 2008–2013, book open 2014–2024, CBS open 2025.
- **Market:** nflverse close.
- **Pushes:** excluded.
- **Method:** each candidate is a signed input f, where positive favors the home side covering. It enters a logistic regression of "home covered" with the live model's logit as a fixed offset, so f must add something to the model.
- **Inputs used:** only games earlier in the same season, so week 1 has f = 0.

Team-game turnover inputs come from nflverse team stats:
- **giveaways** = interceptions thrown + fumbles lost;
- **takeaways** = the opponent's giveaways in the same game;
- **fumble recovery** = the share of all fumbles in a team's games that the team recovered.

The late-score input uses nflverse play-by-play.

## Candidates (6), each "away minus home" so positive favors home (fade the lucky team)

1. **to_last**: net turnover margin (takeaways − giveaways) in the team's previous game.
2. **to_last4**: net turnover margin summed over the previous up-to-4 games.
3. **to_season**: net turnover margin per game, season to date.
4. **fumble_luck**: fumbles recovered minus half of all fumbles in the team's games, season to date.
5. **close_record**: wins minus losses in games decided by 7 points or fewer, season to date.
6. **late_cover_flip**: the previous game's cover result flipped in the last 5 minutes. Coding:
   - +1 if the team was covering its closing line with 5:00 left and finished not covering ("lost it late");
   - −1 for the reverse;
   - 0 otherwise.

## Test

- **Discovery 2008–2013** fixes each candidate's sign.
- **Confirmation 2014–2024** decides: a one-sided test in the discovery sign, Holm-corrected over the 6 candidates at 0.05.
- **2025** (CBS opens) is reported for any pass.
- **Effects** are reported as the cover rate of the side the candidate favors against the rate the live model predicted for that side.

## Decision

A pass becomes a candidate for a separate pre-registered live-tracking rule. Nothing changes the pick from this test
alone. Every candidate is reported, pass or fail.
