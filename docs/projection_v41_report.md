# Projection v4.1: Report (validation failed, not scored)

The rules are in `docs/projection_v41_preregistration.md` (commit `5f9756a`). The full output is in
`data/backtests/projection_v41_validation.json`. By rule, **no 2022–2025 result was computed**.

## Fit (maximum likelihood, 2013–2021, 2,320 games)

| Parameter | Estimate | Approx. SE | Meaning |
|---|---|---|---|
| a | +0.216 | 0.011 | Game environment raises TDs for both teams |
| b | −0.252 | 0.014 | …and lowers FGs for both |
| c, d | about 0 | 0.04 / 0.07 | Team finishing factor: not used by the fit |
| e, f | +0.049 / −0.261 | 0.013 / 0.017 | Dominance factor, mostly through FGs. The sign of (e, f) is arbitrary |
| n_TD, n_FG | 9 / 8 | — | The **smallest** allowed trials (max observed + 1): the data want the least possible variability |

The binomial cap bound on 0.5% of cells.

**Estimator check.** On simulated data with known parameters, the fitted likelihood beat the true parameters'.
The surface has a flat ridge (finishing vs dominance), so individual loadings are weakly identified. The
Hessian SEs understate that; predictions are unaffected.

## Validation

| Check | Result | Required | Verdict |
|---|---|---|---|
| TD reconciliation / neutral / point-in-time | 99.87% / 0 / ≤ 2 × 10⁻¹⁶ | — | Pass |
| Max gap, implied vs observed residual correlations | 0.091 | ≤ 0.05 | **Fail** |
| TD dispersion, implied vs observed | 0.825 vs 0.774 | ±0.05 | **Fail** (by 0.001) |
| FG dispersion | 0.996 vs 0.981 | ±0.05 | Pass |
| 50% coverage, training | 0.551 | 0.47–0.53 | **Fail** |
| PIT deciles, training | lowest 0.073 | 0.08–0.12 | **Fail** |
| Internal holdout (fit 2013–18, check 2019–21) | coverage 0.523 | 0.46–0.54 | Pass |

**Residual correlations** of [TD_h, FG_h, TD_a, FG_a]:

| | Observed | Implied |
|---|---|---|
| TD_h–FG_h | −0.242 | −0.151 |
| TD_h–TD_a | +0.158 | +0.143 |
| TD_h–FG_a | −0.162 | −0.092 |
| FG_h–FG_a | −0.070 | −0.007 |

## What the two failures show

1. **Real scoring varies less than any mixing model allows.** TD counts vary less than even the tightest
   binomial. Every latent factor adds variance. So the model cannot use factors to create the strong negative
   TD–FG relationship within a team without overshooting variability, and the fit switched that factor off.
2. **Drive counts alone (v4) also overshoot variability** (0.84), and they get the TD–opponent-FG sign wrong.
3. **The missing mechanism is game script.**
   - Scoring depends on the score: leading teams run clock, and trailing teams take risks and get extra chances.
   - That pulls scores toward each other, which explains the positive cross-team TD correlation. It limits
     how far one team's total can run, which explains the low variability. It turns FG chances into TD
     attempts for the trailing team.
   - Models where each game's counts are drawn at once, like v3, v4 and v4.1, cannot represent a process that
     reacts to the score.

## Status

- v4.1 is **not adopted**. v3 stays the tracked projection.
- Calibration by 50%-interval coverage (training seasons):

  | Model | Coverage |
  |---|---|
  | v3 (Poisson) | 61.7% |
  | v4 (drives) | 54.3% |
  | v4.1 | 55.1% (holdout 52.3%) |

  Both successors improved a lot, but neither met its pre-registered bar.
