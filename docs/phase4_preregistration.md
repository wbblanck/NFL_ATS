# Phase 4 — Cover-Probability Engine: Pre-registration

Committed **before** any Phase 4 evaluation was run.

## Model

- **Predicted margin** = −(market home spread at lock). The market's number is
  the prediction; Phase 6 may add residual features later.
- **Needed:** P(home margin > −S | market spread c) for any half-point frozen
  line S. Then P(away) = 1 − P(home). No push is possible when S is x.5.

## Candidate estimators of F(t | c) = P(margin > t | c)

- **N — Normal.** margin ~ N(−c, σ). σ is fit on the training seasons.
- **E — Shifted discrete empirical.** Residual r = margin + c.
  F(t | c) = share of training games with r > t + c. Each game's full outcome
  is kept, but the margin lattice is shifted by c, so key numbers (3, 7, 10,
  14) are *not* kept fixed in margin space.
- **K — Kernel-local empirical (unshifted).** F(t | c) is a weighted share of
  training games with margin > t. Game i gets weight exp(−½((cᵢ − c)/h)²).
  Margins are used as they are, so key-number mass stays where it occurs in
  real outcomes. The bandwidth h is chosen from {0.5, 1, 1.5, 2, 3} by log
  loss on the last 3 training seasons, trained on the seasons before those.
  Nothing from the test season is used.
- **KS — K with symmetry pooling.** Each training game also enters mirrored
  (c → −c, margin → −margin). This doubles the effective sample and assumes
  favorites and underdogs are symmetric around the spread.

## Evaluation

- **Walk-forward, one season at a time.** Test seasons are 2007–2021. The
  target is whether the home team covered the **SBRO opening line**, which
  stands in for the frozen line. **c** is the nflverse close, standing in for
  the market at lock.
- **Training:** all regular-season games with a nflverse close and score from
  seasons *before* the test season (1999 onward).
- **Games excluded from scoring:** those landing exactly on a whole-number
  open (pushes), and those with a missing open. Both are counted.
- **Metrics:**
  - **Primary:** pooled out-of-sample log loss.
  - **Also reported:** Brier score, per-season log loss, and the ATS win rate
    of "pick the higher-probability side" versus the D0-full drift rule on
    the same games.

## Decisions fixed in advance

1. **Estimator choice:** the estimator with the lowest pooled out-of-sample
   log loss becomes the engine's default.
2. **Live pick rule:** it switches from D0-full to "higher probability side"
   **only if** the argmax rule's pooled out-of-sample ATS win rate is at
   least D0-full's on the same games. Otherwise D0-full stays, and
   probabilities are reported alongside the pick.
3. **Gate (technical):**
   - P(home) + P(away) = 1 for every half-point line.
   - Whole-number lines are rejected in league mode.
   - A spread-sensitivity table (the line ±3 points in half-point steps) is
     produced.
