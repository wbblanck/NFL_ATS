# Projection v4: Report (validation failed, not scored)

The rules are in `docs/projection_v4_preregistration.md` (commit `77af4d6`). The validation output is in
`data/backtests/projection_v4_validation.json`. By rule, **no 2022–2025 result was computed for v4**.

## Validation results (training seasons 2013–2021 unless noted)

| Check | Result | Verdict |
|---|---|---|
| TD reconciliation, 1999–2025 | 99.87% of 13,912 team-games reconcile with pbp TDs, against 96.8% with `team_stats`. The 18 exceptions are 16 in 2001–02 and 2 in 2011 | Pass |
| Neutral sites | 67 completed neutral REG games; none carries home = 1 | Pass |
| Point-in-time | 13 games rebuilt; max difference 2 × 10⁻¹⁶; same starters | Pass |
| Do the problems exist in training? | TD dispersion 0.77; cross-team TD residual correlation +0.16; the Poisson 50% interval holds 61.7% of results | Yes, so fix 3 applies |
| **Drive-model fit** | 50% interval holds **54.3%** (required 46–54%). Cross-team TD correlation implied **0.066** vs observed 0.157 (required within ±0.07) | **Fail** |

The drive model improved calibration a lot. The Poisson PIT deciles are
0.05 / 0.08 / 0.11 / 0.12 / 0.13 / 0.14 / 0.13 / 0.09 / 0.09 / 0.06; the drive model's are
0.08 / 0.10 / 0.10 / 0.11 / 0.11 / 0.12 / 0.12 / 0.09 / 0.09 / 0.10. But it misses the pre-registered bar.

## Why it failed (training-season residual structure)

| Correlation of residuals | Observed | Drive model |
|---|---|---|
| TD vs own FG | −0.24 | about −0.15 |
| Home TD vs away TD | +0.16 | +0.07 |
| TD vs opponent FG | −0.16 / −0.13 | positive |
| Home FG vs away FG | −0.07 | positive |
| TD dispersion (Poisson = 1) | 0.77 | 0.84 |
| FG dispersion | 0.98 | 0.90 |

- Real games shift **both** teams between touchdowns and field goals together, through conditions like
  weather, officiating and game script. Shared drive counts alone cannot produce that. They make every
  scoring type rise together.
- Each team's score is also slightly too variable under the drive model.
- Drives per team have fallen from 12.8 (1999) to 10.8 (2025). The frozen 2013–2021 distribution (mean 11.7)
  would be stale for recent seasons in any case.

## Status

- v4 is **not adopted** and not recorded live. v3 stays the tracked projection.
- Fixes 1 (pbp TDs) and 2 (neutral sites) passed their checks. They are data corrections that any successor
  model will include.
- A successor needs its own pre-registration: a score distribution that reproduces the observed dependence
  structure, fitted on training seasons only.
