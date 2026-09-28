# Line-Movement Model + EPA/Efficiency Differentials: Pre-registration

Committed **before** any result of this test was computed.

## What the user asked for

"It uses the original model but with EPA differentials and efficiency metrics. The original model I mean the line
movement one."

- **Base:** the live pick model, `total-shifted-empirical-argmax`: the market at lock (spread and total) vs the
  frozen league line.
- **The test:** add opponent-adjusted EPA and efficiency *differentials* between the two teams, and check whether
  they improve its cover probabilities and picks.

## Disclosed in advance

- **Phase 6 already tested one EPA feature on this model and failed.** The feature was net EPA/play, and the base
  was the earlier market-only estimator, on the same 2010–2021 games.
  - This test is broader: four metrics, split pass and run, plus success rate and red-zone rate. It uses the
    current live base.
  - It is still a **second look at the same seasons**, and the result must be read that way.
- **Related evidence:** the v6 score-projection test found the market already prices these metrics. When v6
  disagreed with the closing line by 3+ points, it was right 49% (2022–2024) and 42% (2025).
- **Expected result:** no improvement. It is reported either way.

## Base probabilities (walk-forward; the same proxies as phases 3–7)

- For each season s in 2007–2021: `TotalDist("shifted_total")` is fit on 1999 to s−1. It gives P(home covers the
  frozen line) using the market close (spread and total).
- **Frozen line:** SBRO open. **Market at lock:** nflverse close. Pushes on the open are excluded.

## Features: four differentials, home perspective

- **Ratings:** `features/efficiency_v6.py`, i.e. the same play filters, metrics and point-in-time ratings as v6.
- **Hyperparameters are fixed a priori, not tuned on any outcome.** Phase 6's values are used: half-life
  h = 6 games, season shrink s = 0.5. (v6's tuned 8 / 0.6 is **not** used, because it was chosen on 2017–2021
  margins, which are test seasons here.)
- For each metric m ∈ {`db` (EPA/dropback), `rush` (EPA/designed rush), `sr` (success rate), `rz` (red-zone TD
  rate)}:
  - `d_m` = (home offense m + away defense-allowed m) − (away offense m + home defense-allowed m)
  - In words, the home team's expected edge on that metric in this matchup.

## Model and comparators (as in phase 6)

- **Model:** logit(p) = a + b·logit(p_base) + γ·[d_db, d_rush, d_sr, d_rz].
  - Fit walk-forward: test season s uses only seasons before s.
  - Test seasons 2010–2021.
- **Comparators:**
  - **raw:** p_base, no refit;
  - **platt:** the same refit with no features.

## Decision rules (fixed in advance)

1. **Primary (decides):** the four-feature model is **kept** only if all three hold:
   - its pooled out-of-sample log loss is lower than raw's;
   - its pooled out-of-sample log loss is lower than platt's;
   - its ATS win rate (pick P > 0.5) is ≥ raw's on the same games.

   This is the phase 6 rule.
2. **Confirmation 2025 (CBS open, half-point lines):**
   - The residual model is fit on the 2007–2021 out-of-sample rows and applied to 2025. The base is fit on
     1999–2024.
   - If the model is kept, 2025 log loss must also be ≤ the live model's. Otherwise it is reported as not
     confirmed.
3. **Live change:** only if 1 and 2 both pass. Even then it is **proposed to the user**, not switched
   automatically.
4. **Diagnostics (reported, never decisive):**
   - the two EPA differentials alone, and the two efficiency differentials alone;
   - γ per test season;
   - picks changed vs raw;
   - correlation of each differential with the margin the market missed (margin − (−close)).

Seasons 2022–2024 have no verified opening-line proxy and are not used.
