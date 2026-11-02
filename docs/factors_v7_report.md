# Team-stat factors model, 10k simulations (`proj-factors-v7`): Report (failed; not tracked)

- **Rules:** `docs/factors_v7_preregistration.md` (commit `903baf0`), committed before any feature or result.
- **Code:** `src/engine/backtest/factors_v7.py`.
- **Numbers:** `data/backtests/factors_v7.json`. Regenerate with
  `python -m engine.backtest.factors_v7 --cache <dir>`. The cache holds `pbp_<season>.parquet` for 2005–2026.

## Result

**Not kept.** All nine team stats, combined in one model and simulated 10,000 times per game, project scores about
as well as v1 and no better. The model has no edge against the closing line. In 2026 it trails the official pick.

- **Tracking rule:** it needed a lower Test A margin MAE than v1 **and** ATS vs the close above 50% at z ≥ 1.0. It
  failed both: margin MAE 10.05 vs v1's 9.98, and ATS 49.3%.
- **Live-pick rule:** it needed z ≥ 1.96 against the live model on Test B plus 2026. Combined it was 76–70 on the
  146 games where the picks differed (z ≈ 0.5). It fails.

## Validation (all passed before results were read)

| Check | Result |
|---|---|
| Point in time (2 games per season, 2006–2025) | 0 mismatches in 720 values |
| Simulated vs analytic mean points | 0.096 points on average (bar 0.1) |
| Training projected vs actual points (TD, XP, 2-pt, FG) | 22.25 vs 22.00 (bar 0.5) |
| End-of-season points/drive vs points/game | r = 0.937 (bar 0.8) |
| Games dropped for a missing value | 2005 (warm-up, no prior-season mean) plus 6 games (no red-zone drive yet) |

## Test A: 2022–2024, weeks 3–18 (718 games)

| Measure | v7 factors | v1 | Market close |
|---|---|---|---|
| Team score MAE | **7.40** | 7.43 | — |
| Margin MAE | 10.05 | 9.98 | **9.41** |
| Total MAE | 10.39 | 10.60 | **10.11** |
| Straight-up winner | 64.3% | 63.7% | — |
| Margin log-likelihood | −4.000 | −4.000 | — |
| ATS vs close | 49.3% (342–352) | 50.7% (352–342) | — |

On the 198 games where v7 and v1 picked differently against the close, v7 went 94–104.

## Test B: 2025, weeks 3–18 (240 games)

| Measure | v7 factors | v1 | Market close |
|---|---|---|---|
| Team score MAE | 7.58 | **7.43** | — |
| Margin MAE | 10.69 | 10.49 | **10.08** |
| Total MAE | 10.59 | **10.46** | 10.13 |
| Straight-up winner | 58.6% | 61.9% | — |
| ATS vs close | 49.4% | 49.8% | — |

- **ATS vs the CBS open:**
  - v7 went 124–112 (52.5%) and the live model 116–120 (49.2%).
  - On the 104 games where they differed, v7 won 56–48 (z = 0.78). That is within noise.

## 2026 live, weeks 3–8 (77 games with an official pick)

| vs pool line | Record |
|---|---|
| Official pick | **41–36** (53.2%) |
| v7 factors | 39–38 (50.6%); 20–22 on the 42 games where it differed from the official pick |
| v1 / v3 / v7 on the 70 games with logged projections | 39–31 / 37–33 / 35–35 |

| Score accuracy (70 games) | v7 | v1 | v3 |
|---|---|---|---|
| Team score MAE | 7.52 | **7.35** | 7.43 |
| Margin MAE | 9.40 | **8.94** | 9.16 |
| Total MAE | 11.53 | 11.38 | **11.35** |
| Winner | 59.4% | **60.9%** | 58.0% |

The game-by-game 2026 table was delivered outside the repo. It is not committed.

## What the fit says

- **Most of the weight is in points per drive and EPA per play** (offense and the opponent's defense allowed).
  - TD coefficients per SD: off_ppd +0.063 (SE 0.021), def_ppd +0.051 (0.018), off_epa +0.113 (0.071).
- **The other seven metrics add little once those two are in:**
  - passing and rushing EPA, success rate, explosive rate, sack rate, third down, red zone.
  - Most of their coefficients are within 2 SE of zero, and several carry the "wrong" sign. That is what happens
    when correlated stats are fit together.
- **This matches phase 8 and v6.** The market already prices efficiency, so adding efficiency stats does not beat it.
- **The 10,000 simulations change nothing material.** They reproduce the analytic means to within 0.1 points. v1
  and v3 already compute the exact distribution.
