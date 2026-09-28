# Line-Movement Model + EPA/Efficiency Differentials: Report (failed; live model unchanged)

- **Rules:** `docs/phase8_efficiency_preregistration.md` (commit `d18dd10`), committed before any result.
- **Code:** `src/engine/backtest/efficiency_residual.py`.
- **Numbers:** `data/backtests/phase8_efficiency.json`.

## Result

**Not kept.** Adding EPA and efficiency differentials to the live line-movement model made its probabilities
slightly worse and its picks slightly worse. The live model stays as it is.

## Base check (before any result was read)

- The walk-forward base reproduces the published live-model backtest exactly: 3,722 games, 2043–1679, as in
  `docs/total_report.md`.
- All 2,979 test games (2010–2021) have all four differentials. None is missing.

## Primary test: walk-forward 2010–2021, 2,979 games (SBRO open as frozen line, nflverse close as market)

| Model | Log loss | Brier | ATS | Picks changed vs live |
|---|---|---|---|---|
| **Live model (raw)** | **0.68728** | **0.24711** | **54.45%** (1622–1357) ± 0.91 | — |
| Refit, no features | 0.68823 | 0.24752 | 54.45% | 0 |
| **+ all four differentials (decides)** | 0.68955 | 0.24817 | 54.15% (1613–1366) | 41 |
| + EPA only (dropback, rush) | 0.68890 | 0.24786 | 54.31% | 22 |
| + efficiency only (success rate, red zone) | 0.68867 | 0.24772 | 54.41% | 3 |

- **The rule required** lower log loss than both the live model and the refit, and ATS ≥ the live model's.
- **The four-feature model failed all three conditions.**
  - Its log loss is higher than both the live model and the refit.
  - It changed 41 picks and lost 9 net wins: 54.15% vs 54.45%.
- The two diagnostic subsets fail the same way.

## Confirmation 2025 (CBS open, 210 half-point games)

| Model | Log loss | ATS |
|---|---|---|
| Live model | **0.6903** | 108–102 |
| Live + differentials | 0.6904 | 108–102 (0 picks changed) |

**Not confirmed** (not needed, since the primary test already failed).

## Why: the market already prices these differentials

| Differential | corr with market spread | corr with final margin | corr with what the market missed |
|---|---|---|---|
| EPA per dropback | 0.78 | 0.34 | **0.025** |
| EPA per designed rush | 0.56 | 0.25 | **0.021** |
| Success rate | 0.76 | 0.34 | **0.023** |
| Red-zone TD rate | 0.30 | 0.12 | **0.002** |

- **The differentials are real team-strength signals.** They correlate with the spread and with the final margin,
  and the ratings passed their validation in `docs/projection_v6_report.md`.
- **But they carry no information about the part of the margin the market got wrong.** Correlations of 0.00–0.03
  over 3,722 games are indistinguishable from zero.
- **The fitted weights (γ) change sign from season to season.** For example, EPA/dropback runs from −0.60 in 2010
  to +0.10 in 2019. That is noise-fitting, not a stable effect.

This is the third test pointing the same way: phase 6's net EPA, v6, and now this one.
- The line-movement model's edge comes from the pool line being **frozen** while the market moves.
- It does not come from knowing football facts the market doesn't. By lock, the market has those.
