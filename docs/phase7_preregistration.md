# Phase 7 — Full-System Walk-Forward: Pre-registration

Committed **before** the Phase 7 backtest was run.

## System under test (frozen as of this commit)

- `phase4-shifted-empirical-argmax`: market-only.
- P(home covers) comes from the shifted-empirical margin distribution given
  the market at lock. The pick is the higher-probability side.
- No calibration (Phase 5) and no residual features (Phase 6).

## Period and data

- **Test seasons: 2007–2021, regular season, one season at a time.**
  - 2007 is the start because it is the first season with an opening-line
    proxy (SBRO 2007-08).
  - 2021 is the end because it is the last SBRO season. No verified
    frozen-line proxy exists for 2022–2025 (audit 0.4).
- **Training:** for each test season, all nflverse regular-season games with a
  close and a score from 1999 up to the season before. The only fitted object
  is the empirical margin distribution, and it has no hyperparameters.
- **Frozen line:** SBRO open (proxy for the CBS Tuesday line).
- **Market at lock:** nflverse close (proxy).
- **Pushes:** games landing on a whole-number open are pushes (the P column),
  excluded from win rate. Games with no usable open are excluded and counted.

## Kill criterion

- Pooled ATS win rate p, with SE = sqrt(p(1−p)/N).
- **FAIL** unless (p − 0.5137) / sqrt(SE² + 0.0082²) ≥ 1.96, where 0.5137 is
  the best Phase 2 baseline (always away, SBRO open).
- A FAIL is reported plainly and stops Phase 8.

## Disclosed in advance

**This is not independent confirmation.** The same 2007–2021 games were used
in Phases 3–6 to choose the rule, the estimator and the calibration. Phase 7
re-runs the frozen system end to end and reports the full metric set. The
**independent** test is live 2026+ play against the *actual* CBS league line.

## Live evaluation plan (pre-registered now)

- Every final prediction in `data/predictions/predictions.csv` is graded
  against the recorded league line and the final score.
- The live record is reported cumulatively with SE, and there is no
  filtering.
- **No live claim of skill before 256 graded games.** At 256 games the SE is
  about 3.1 pp, so even 56% would sit only about 2 SE above 50%.

## Metrics, per season and pooled

- ATS W-L-P, win rate and SE.
- MAE and RMSE of the margin, for both the expected margin (−market) and the
  median margin.
- Log loss, Brier and ECE, using the Phase 5 buckets.

## Diagnostic subgroups (never used to filter picks)

- **Frozen spread size:** |S| ≤ 3, 3.5–7, > 7.
- **Pick side:** home or away.
- **Pick role:** favorite or underdog.
- **Part of season:** weeks 1–6, 7–12, 13+.
- **Drift size:** 0, 0.5, ≥ 1.
