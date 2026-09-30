# Pace and Penalties: Report

Rules: `docs/pace_penalty_preregistration.md` (committed before any result). Numbers:
`data/backtests/pace_penalty.json`; code `engine/backtest/pace_penalty.py`.

## Result: fail

| 2020–2024, half-point book opens (705 games) | With pace + penalties | Live model |
|---|---|---|
| Record | 385-320 (54.6%) | 394-311 (55.9%) |
| Games where the picks differ (27) | won 9 | won 18 |
| Log loss | 0.6833 | 0.6826 |

z = −1.73 (needed ≥ +1.645) and a higher log loss: rules (a) and (b) fail. 2025 CBS opens: the picks differed in
4 games, 3-1 for the new model (rule (c) holds, but it cannot rescue (a) and (b)).

## What the inputs carry (fit on 2008–2019, no penalty, reported only)

| Input | Weight | Standard error | Reading |
|---|---|---|---|
| Live model (logit) | 0.93 | 0.17 | the market move does the work |
| Penalty edge (per 10 net yards/game) | −0.006 | 0.033 | nothing: 0.2 SE |
| Pace × favorite | +0.046 | 0.033 | 1.4 SE, not significant; a faster game helps the favorite very slightly |

Validation chose the same grid-edge settings as the adaptive test (no age decay, largest penalty λ = 10), and even
then its 2016–2019 log loss (0.68797) was just above the live model's (0.68782).

## Conclusion

Team discipline (net penalty yards) carries no information against the spread once the market move is known.
Pace shows at most a faint, non-significant lean toward favorites in fast games. Neither improves the picks. The
live model is unchanged.
