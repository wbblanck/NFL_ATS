# Overlooked Patterns: Pre-registration

Committed before any result below. Purpose: check a fixed list of situational patterns that have not been tested,
each asking "does this situation predict covers against the stale line **beyond** what the live model already
says?". Everything listed in docs/*_report.md was already seen; one observation from it motivates candidate 3
(no-move games won 46% in 2014–2024, docs/edge2_report.md).

## Data

The adaptive-test game set (`engine.backtest.adaptive_eval.dataset`): 2008–2025 regular season, stale line =
SBRO open 2008–2013, book open 2014–2024, CBS open 2025; market = nflverse close and total; live-model cover
probability fit on earlier seasons; pushes excluded. Situational fields from the nflverse schedule.

## Candidates (15), each a signed input f (positive favors the home side covering)

Notation: dir = +1 if the market moved toward home (close below the line), −1 toward away, 0 no move;
dog = +1 if home is the underdog on the line, −1 if away is.

1. **home_dog**: 1 if the home team is the underdog, else 0.
2. **dog**: dog (underdogs in general).
3. **nomove_home**: 1 in no-move games (the home side), else 0.
4. **move_to_dog**: dir when the move is toward the underdog, else 0 (is that move more reliable?).
5. **move_to_fav**: dir when the move is toward the favorite, else 0.
6. **early_move**: dir in weeks 1–4, else 0 (market less settled early).
7. **late_move**: dir in weeks 15–18, else 0.
8. **key_cross**: dir when the line and the close are on different sides of 3 or 7 (absolute), else 0.
9. **division_dog**: dog × division game.
10. **primetime_dog**: dog × primetime (Thursday, Monday, or kickoff at or after 19:00 ET).
11. **big_fav_dog**: dog × (|line| >= 10).
12. **rest**: sign(home rest days − away rest days).
13. **bounce**: (home lost its previous game by 14+ as a favorite) − (away did).
14. **ats_fade**: (away covered each of its last 3 closing lines) − (home did): fade hot teams.
15. **wind_dog**: dog × (outdoor and wind >= 15 mph). Uses the recorded game-day wind (close to, not exactly,
    what was known at lock; disclosed).

## Test

Logistic regression of "home covered" on f with the live model's logit as a fixed offset (so f must add to the
model). Discovery 2008–2013 fixes each sign. **Confirmation 2014–2024** (decides): one-sided test in the discovery
sign, Holm-corrected over all 15 at 0.05. 2025 CBS opens reported for any pass. Effect sizes are reported as the
cover rate of the f-favored side against the rate the live model predicted for it.

## Decision

A pass is a candidate for a pre-registered live-tracking rule; nothing changes the pick from this test alone.
Every candidate is reported.
