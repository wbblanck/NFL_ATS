# Adaptive In-Season Model: Pre-registration

Committed before any result of this model was computed. Earlier results already seen (disclosed): every test in
docs/*_report.md, including the live model by season and by move size, v1/v3/v6 against the market, and the hybrid.

## Idea

Two layers that update every week of the season.

**Layer 1: team ratings updated by a Kalman filter** (`adaptive-kalman`).
- One net rating per team, in points. Predicted home margin = home edge + rating(home) − rating(away).
- Before each game the uncertainty of both teams grows by q (form changes). At a new season every rating is
  shrunk toward 0 by s and its uncertainty is widened by p0.
- After each game two measurements update both teams: the final margin (noise variance R) and the efficiency
  margin k·(EPA per play of home − away offense, garbage time removed; noise variance R·ρ). k is fit on
  training seasons only.
- Home edge: mean home margin of the previous 3 seasons.
- Starts in 1999 (warm-up). Hyperparameters (q, s, p0, ρ) chosen on 2007–2015 by the mean squared error of the
  pre-game margin prediction; no line or cover outcome is used.

**Layer 2: a pick model re-fit every week** (`adaptive-pick`).
- Logistic regression for "home covers the pool line" on three inputs:
  1. logit of the live model's cover probability (market move, key numbers, total);
  2. Layer 1's edge over the line: (predicted home margin + line) / 13;
  3. input 2 × [market moved less than 1 point off the line].
- Re-fit before every week on all earlier games since 2008, each weighted 0.5^(age in seasons / H), with an L2
  penalty λ on the three slopes (intercept unpenalized).
- H ∈ {2, 4, 8, no decay} and λ ∈ {0.1, 1, 10} chosen by log loss on 2016–2019 (walk-forward, weekly).
- Pick: home if the fitted probability > 0.5.

## Data

- Proxy pool line: SBRO open 2007–2013; the book's own open (AusSportsBetting: Pinnacle 2014–17, bet365
  2018–24) 2014–2024; CBS odds-page open 2025. Market at lock: nflverse closing spread and total.
- Pushes excluded from training and grading.

## Decision (confirmation 2020–2024, half-point book opens)

- **Pass** if (a) on games where adaptive-pick and the live model differ, adaptive-pick wins more with one-sided
  z ≥ 1.645, (b) its log loss is below the live model's on the same games, and (c) its 2025 CBS-open record on
  differing games is not negative.
- Pass → tracked live beside the official pick; it makes picks only with the user's approval after live tracking.
  Fail → tracked as a comparison only, like the hybrid (if the user wants).
- Also reported, deciding nothing: Layer 1 alone as a pick, Layer 1 margin accuracy vs the market close,
  the fitted weights over time, and results by move size.
