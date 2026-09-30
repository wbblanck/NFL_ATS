# Adaptive In-Season Model: Report

Rules: `docs/adaptive_preregistration.md` (commit `68bd6bd`, before any result). Numbers:
`data/backtests/adaptive.json`; code `engine/models/adaptive.py`, `engine/backtest/adaptive_eval.py`.

## Result: fail

| 2020–2024, half-point book opens (705 games) | Adaptive | Live model |
|---|---|---|
| Record | 384-321 (54.5%) | 394-311 (55.9%) |
| Games where the picks differ (38) | won 14 | won 24 |
| Log loss (lower is better) | 0.6841 | 0.6826 |

z = −1.62 (needed ≥ +1.645) and a higher log loss: rules (a) and (b) fail. On the 2025 CBS opens the two picked
identically in all 210 games (108-102 each).

## Layer 1 (Kalman team ratings)

- Chosen on 2007–2015 margin error: q = 0.5, s = 0.35, p0 = 16, efficiency weight off (ρ = 0; adding the
  EPA measurement did not lower the error). q = 0.5 is the edge of the pre-registered grid.
- Margin error 2007–2015: 193.3 (mean squared) against the closing line's 187.9: less accurate than the market.
- As a pick on its own: 2020–2024 360-345 (51.1%); 2025 CBS 96-114 (45.7%).

## Layer 2 (weekly re-fit)

- Chosen on 2016–2019: no decay of older seasons (H = ∞) and the largest penalty (λ = 10), both grid edges; even
  that setting had a slightly worse validation log loss than the live model (0.6887 vs 0.6878).
- The fitted weight on Layer 1's edge fell from 0.16 (2020 week 1) to 0.01 (end of 2025): as the season data came
  in, the model itself learned that the team ratings add nothing to the market move, and converged back to the
  live model. The low-move games, where it was meant to help, went 13-20 on the games where it differed.

## Conclusion

An adaptive, in-season rating model does not add to the market-move signal, confirming the v1, v3, v6 and hybrid
results with a different method. The live model is unchanged. Not tracked (it differs from the live pick in about
8 games a season, so tracking would say little); it can be added if wanted.
