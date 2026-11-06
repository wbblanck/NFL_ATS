# Batch 2: descriptive numbers before the test (2026-11-06)

Pre-registration: docs/batch2_preregistration.md. The test covers 2026 weeks 10-18 and runs once after week 18
(`python scripts/batch2.py test <cache>`). Everything below is descriptive and is not a result. Numbers:
data/gamesim/batch2_describe.json.

## 2026 weeks 1-8 so far (121 games, all with a pool line; week 9 not yet played)
| Forecast | Right vs pool line | Rate | Margin MAE |
|---|---|---|---|
| Elo | 71 of 121 | 58.7% | 9.770 |
| Simulator | 68 of 121 | 56.2% | 9.820 |
| Average | 73 of 121 | 60.3% | 9.734 |
| Pool line itself | | | 9.806 |

Elo's side matched the official pick in 45.6% of the 79 games compared. Eight weeks of about 15 games is far too few to
read anything from these rates (standard error about 4.5%), and they are the reason the test only counts weeks 10-18.

## 2022-2025 (1,023 games), for the power statement
Margin MAE: Elo 9.964, simulator 9.983 (both reproduce their registered values), average 9.886. Per-game SD of the
paired differences: 1.66 vs Elo, 1.67 vs the simulator, giving a standard error of about 0.15 points at 130 games.
That is close to the 0.13 assumed in the pre-registration, so only a gain of roughly 0.3 points against each model
would be detected.
