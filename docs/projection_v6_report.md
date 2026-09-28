# Projection v6 (`proj-epa-v6`): Report (failed; not tracked)

- **Rules:** `docs/projection_v6_preregistration.md`, committed before any v6 feature or result.
- **Code:** `src/engine/features/efficiency_v6.py`, `src/engine/backtest/projection_v6_eval.py`.
- **Numbers:** `data/backtests/projection_v6.json`. Regenerate with
  `python -m engine projection-v6 --cache <dir>`.

## Result

**v6 does not improve on v1 and is worse than v3.** Under the pre-registered rule it is recorded as tested and
**not tracked**. v3 stays the tracked projection, and the live pick is unchanged.

Adding opponent-adjusted EPA per dropback, EPA per rush, success rate and red-zone TD rate to the original model
produced no measurable gain in projecting scores. It also produced no edge against the closing line or the CBS
open.

## Test A: 2022–2024, 815 games (all three models on the same games)

| Measure | v6 (v1 + efficiency) | v1 (original) | v3 (players) | Market close |
|---|---|---|---|---|
| Margin log-likelihood (higher is better) | −3.9976 | −3.9964 | **−3.9900** | — |
| Margin MAE (points) | 9.91 | 9.93 | 9.92 | **9.42** |
| P(home wins) log loss | 0.6437 | 0.6434 | 0.6354 | **0.6079** |
| ATS vs the close | 51.5% ± 1.8 (405–382) | 51.2% | 49.9% | — |

- **v6 − v1 margin log-likelihood:** −0.0012 ± 0.0022 (z = −0.5). No difference.
- **v6 − v3:** −0.0077 ± 0.0044 (z = −1.7). v6 is worse.
- **Decision rule:** v6 needed to beat **both** v1 and v3. It beat neither, so it **fails**.
- **ATS vs the close:** 51.5% is within 1 SE of 50%. The paired sign tests are within noise: v6 vs v1 z = 0.25,
  v6 vs v3 z = 1.0.
- **v6 vs the market:** 0.49 ± 0.11 points worse in MAE.

## Test B: 2025, 272 games

| Measure | v6 | v1 | v3 | Market / live |
|---|---|---|---|---|
| Margin log-likelihood | −3.9758 | −3.9762 | **−3.9607** | — |
| Margin MAE | 10.20 | 10.16 | 9.91 | **9.72** (close) |
| ATS vs the close | 48.7% (132–139) | 49.4% | 51.3% | — |
| ATS vs CBS open, half-point lines (210) | 48.1% | 51.0% | 49.5% | 51.4% (live) |

- **Log loss vs the CBS open:** v6 0.718, live 0.690.
- **Paired v6 vs live:** z = −0.73.
- **The switch bar is nowhere near met.** The live pick would need z ≥ 1.96 and lower log loss.

## Does v6 know anything the market doesn't? No.

| Diagnostic | Test A | Test B |
|---|---|---|
| corr(v6 margin − close, actual margin − close) | −0.02 | −0.06 |
| Games where v6 and the close differ by ≥ 3 points: v6's side covers | 49.1% ± 2.9 (291 games) | 41.6% ± 5.6 (77 games) |

When v6 disagrees with the market, the market is right at least as often. This repeats phase 6: the market already
prices EPA.

## What the model learned (β fit on 2006–2021, 8,224 team-games)

| Feature | TD β (SE) | FG β (SE) |
|---|---|---|
| off_db (EPA/dropback) | +0.05 (0.11) | −0.29 (0.14) |
| off_rush (EPA/rush) | −0.01 (0.16) | −0.39 (0.19) |
| off_sr (success rate) | +0.92 (0.52) | +0.25 (0.65) |
| off_rz (red-zone TD rate) | **−0.70 (0.13)** | **+1.00 (0.16)** |
| def_db (allowed) | −0.15 (0.11) | −0.24 (0.14) |
| def_rush (allowed) | −0.05 (0.16) | −0.02 (0.20) |
| def_sr (allowed) | −0.09 (0.55) | +0.04 (0.68) |
| def_rz (allowed) | **−0.78 (0.13)** | **+1.06 (0.16)** |

- **The EPA terms add almost nothing beyond v1.** The β values are near zero once v1's own rating is the baseline.
  v1's time-decayed scoring ratings already carry the team-strength signal EPA measures, at least for projecting
  scores.
- **The one clear signal is red-zone regression.** Teams that have been converting (or allowing) red-zone TDs at a
  high rate score *fewer* TDs and kick *more* FGs than v1 expects.
  - v1 over-credits red-zone finishing, which is largely luck and regresses toward average.
  - This shifts points between TDs and FGs, so it barely moves the margin, and it did not improve the out-of-sample
    margin likelihood.
  - This is a hypothesis for a future pre-registered test on the TD/FG split. It is **not** a result that changes
    anything now.

## Tuning (training seasons only: fit 2006–2016, scored on 2017–2021, 1,296 games)

| h (games) | s | Inner margin LL |
|---|---|---|
| 4 | 0.3 | −4.03083 |
| 4 | 0.6 | −4.03051 |
| 8 | 0.3 | −4.03083 |
| **8** | **0.6** | **−4.03043** |
| 16 | 0.3 | −4.03102 |
| 16 | 0.6 | −4.03045 |

- v1 on the same block scored −4.03202.
- The inner-block gain of +0.0016 did not hold out of sample: Test A −0.0012, Test B +0.0005.

## Validation (all passed before any test season was scored)

1. **Point-in-time: max difference 0.0** over 40 seeded games, 2006–2025.
   - **Disclosure:** the first run failed with differences up to 3e-7.
   - Cause: nflverse has no kickoff times for 1999, the warm-up season. The check's "kickoff before this game" cut
     dropped all of 1999, while the model processed it first in week order, which is correct.
   - Fix: a missing kickoff time now falls back to the game date, for both ordering and the check.
   - The model's features were unchanged (max 1e-16), so the tuning stood. Committed in `8e1ea68` before
     scoring.
2. **β = 0 reproduces v1:** difference 0.0 on 272 games of 2023, plus a unit test.
3. **Ratings are sensible.**
   - End of 2023, best dropback offenses: SF, MIA, DAL, CIN, GB. Worst: NYJ, CAR, NE, NYG, CLE.
   - Best pass defenses: BAL, CLE, BUF, NYJ, KC. Worst: WAS, ATL, IND, ARI, SEA.
   - Net rating vs season point differential, 2006–2021: **r = 0.87** over 512 team-seasons (required > 0.6).
4. **Coverage:** 99.98% of 10,398 team-games have play data.
   - The only gap is 2011 week 14 OAK @ GB, which is missing from nflverse play-by-play. Its ratings carry over.
5. **Filters:**
   - The garbage-time rule removes 29–34% of counted plays each season, about 31% on average. It is the
     pre-registered rule and was not changed.
   - Red-zone drives: 3.0–3.2 per team-game. 8–20 team-games per season had no red-zone drive.

## Status

- v6 is not wired into the live runs, and v3 remains the tracked projection.
- The picks are unchanged: market drift vs the frozen league line.
