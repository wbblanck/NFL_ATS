# Projection v5.1: Report (validation failed, stop rule triggered)

The rules are in `docs/projection_v51_preregistration.md`: commit `3d29770`, plus an amendment committed before
the run (`8ffde1c`). The output is in `data/backtests/projection_v51_validation.json`. By rule, **no 2022–2025
result was computed, and the projection-distribution track stops here.** v3 stays the tracked projection.

## Validation

| Check | Result | Required | Verdict |
|---|---|---|---|
| Data (TD reconciliation / neutral / point-in-time) | 99.87% / 0 / identical | — | Pass |
| Late TD share, trailing 9–16 vs leading 9–16 (Q4 > 5:00) | data 29.0% vs 19.7%; model 30.3% vs 18.9% | trailing > leading | Pass |
| Environment factor (SMM, 2013–2021) | a = 0.3 (TD), b = 0 (FG) | — | — |
| Points per team | 23.68 vs 23.03 | ±0.3 | **Fail** |
| Drives per half | 11.87 / 12.09 vs 11.32 / 11.39 | ±0.3 each | **Fail** |
| TD / FG dispersion | 0.872 / 1.014 vs 0.774 / 0.981 | ±0.05 | **Fail** (TD) |
| 50% coverage (training) | 0.524 | 0.47–0.53 | Pass |
| PIT deciles | 0.084–0.113 | 0.08–0.12 | Pass |
| Margins of exactly 3 / 7 | 12.3% / 6.6% vs 14.2% / 8.7% | ±1.5 pp | **Fail** |
| Out-of-sample dependence (fit 2013–18, check 2019–21) | max gap 0.052 | ≤ 0.05 | **Fail** (by 0.002) |
| Out-of-sample calibration | coverage 0.496 | 0.46–0.54 | Pass |

**Residual correlations (training)** of [TD_h, FG_h, TD_a, FG_a]:

| | Observed | Simulated |
|---|---|---|
| TD_h–FG_h | −0.242 | −0.210 |
| TD_h–TD_a | +0.158 | +0.185 |
| TD_h–FG_a | −0.162 | −0.150 |
| FG_h–FG_a | −0.070 | −0.040 |

## The series, v3 → v5.1 (training seasons)

| | v3 (Poisson) | v4 (drives) | v4.1 (latent) | v5 (simulator) | v5.1 |
|---|---|---|---|---|---|
| 50% coverage (target 0.47–0.53) | 0.617 | 0.543 | 0.551 | 0.538 | **0.524** |
| TD dispersion (observed 0.774) | ≈ 1.0 | 0.84 | 0.83 | **0.775** | 0.872 |
| Cross-team TD correlation (observed 0.158) | 0 | 0.066 | 0.143 | 0.053 | **0.185** |
| Margins of 3 / 7 (observed 14.2% / 8.7%) | — | — | — | 10.5% / 6.2% | **12.3% / 6.6%** |
| Points per team (observed 23.03) | — | — | — | 23.60 | 23.68 |

Each step fixed something, but no version met every pre-registered bar together:
- v5.1 is the first with well-calibrated margins in training *and* out of sample (0.524 / 0.496).
- But the environment factor that restored the cross-team correlation also pushed TD variability back up.
- And the simulator still plays about half a drive too many per half. The excess sits in the final two minutes,
  where real end-of-half sequences (onside kicks, clock stoppages, kneels) are not reproduced by drawing drives
  one at a time.

## Status

- **Stop rule applied.** The projection-distribution work ends here, and v3 stays the tracked projection.
- The two data corrections (play-by-play TDs, no home edge at neutral sites) passed every check they faced. They
  are documented for any future model, but they are **not** applied to the live v3, which stays exactly as
  frozen so that its live record stays meaningful.
