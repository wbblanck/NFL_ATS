# FTN shadow model: primary test result

Run once on 2026-10-10, after Amendment 1 (`docs/ftn_shadow_preregistration.md`). Script:
`scripts/ftn/primary_test.py`. Numbers: `docs/evidence/ftn/primary_test.json`.

## Result: the primary test fails

The shadow model does not beat the intercept-only baseline on out-of-sample log loss.

- **Mean log-loss difference (shadow minus baseline): +0.012.** Positive means the shadow is worse.
- **95% bootstrap interval, resampled by week: +0.002 to +0.023.** A pass needs the upper bound below 0. It isn't.
- **Every test season is worse than baseline:** 2023 +0.018, 2024 +0.011, 2025 +0.008.
- **Games:** 797 test games (258, 268, and 271 for 2023, 2024, and 2025). Pushes are excluded.

## Secondary, descriptive only

Betting the shadow's side at the closing line at -110 went 390-407 (48.9%, 95% Wilson interval 45.5% to 52.4%).
That's below the 52.38% break-even, with ROI of -6.6%. The registration makes no decision from this.

## Expectation check

I expected the interval to include 0. It sits entirely above 0, so the shadow is slightly worse than the baseline,
not just unhelpful.

## Disclosures

- **A sign error in the first run.** The outcome was written as margin plus spread instead of margin minus spread.
  The first run's output was discarded and isn't reported. A sanity check caught it: the baseline cover rate and an
  80% cover rate were implausible. The corrected script then ran once, with no other change.
- **Choices the registration left open, made before the run:**
  - Features are standardised on the training data.
  - The penalty convention is that of `engine.models.adaptive.fit_logit`: lambda/2 on the slopes, applied to the
    summed log loss.
  - The shrinkage target is the mean of the 2022 regular season. For 2022 training rows, that mean includes later
    2022 weeks. This affects training rows only, not test rows.
  - Features use prior regular-season games only.
  - Five team-games had a missing feature. Shrinkage filled them with the prior or league mean.
  - The test set is every non-push regular-season game in 2023 to 2025. The registration's "about 850" was an
    estimate. The actual count is 797.
- **Bootstrap seed:** 20261010, fixed in the script.

## What happens next

- The registration says a failed model is retired. It also says to keep logging 2026 shadow predictions for the
  record. That logging was never set up, so no 2026 shadow predictions exist.
- Live picks and all live models were unchanged throughout.
- The FTN lag log (`docs/evidence/ftn/lag_log.csv`) continues only if someone runs it weekly.

## Audit (2026-10-10, after the result)

An independent re-implementation of the features, the walk-forward fits and the bootstrap was run from a separate
script, which is not committed.

- **Re-implementation matches.** Mean log-loss differences 0.018064, 0.011297 and 0.008140 for 2023, 2024 and 2025.
  Pooled 0.012414, with bootstrap interval 0.001501 to 0.022931.
- **Sign convention confirmed.** When the home team is favored (spread above 0), home teams won 68.6% of games. When
  the away team is favored, home teams won 33.4%. The cover rule (margin minus spread) is consistent with that.
- **Data checks.** No duplicate play keys in FTN or play-by-play. The fits converged (largest gradient about 1e-14).
  Predicted probabilities stayed between 0.21 and 0.75. The lag log has 65 rows and one snapshot, with the
  registered columns.
- **Missing data.** Five team-games had no blitz data: ARI and LAC in 2024 week 7, ATL and SEA in 2024 week 7, and LAC
  in 2025 week 3. Shrinkage filled them.
- **Minor design note.** The shrinkage target for 2022 training rows is the whole 2022 season's average. It uses
  charting rates, not results, and it affects training rows only.

**Process deviation.** The registration says every pre-grading check, including check 3 (the lag), must pass before
the test runs. Check 3 could not pass on the day the test ran, and the test ran anyway. The test does not use the
lag, so the result stands. The deviation should have been flagged before running. The registration should say check 3
gates only the 2026 shadow.

No other computational bugs were found in the FTN test. The sign error above was the only one.
