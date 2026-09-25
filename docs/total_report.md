# Game-Total Fix: Report

The rules were pre-registered in `docs/total_preregistration.md` (commit
`e5e1893`) before any result. The raw numbers are in
`data/backtests/total_results.json`, from `engine.backtest.total.run()`.

## Primary test (decides): walk-forward 2007–2021, 3,722 games — **PASS, adopted**

| Estimator | Log loss | ATS |
|---|---|---|
| shifted (previous live) | 0.68623 | 54.89% (2043-1679) |
| **shifted_total** | **0.68603** | 54.89% (2043-1679) |
| normal_total | 0.68627 | 54.89% |

The pre-registered rule is: lower log loss **and** ATS ≥ shifted. Only
`shifted_total` meets it, so it is adopted.

## Confirmation 2025 (CBS open, 210 half-point games; reported only)

| Estimator | Log loss | ATS |
|---|---|---|
| shifted | 0.6919 | 108-102 |
| shifted_total | **0.6903** | 108-102 |

## What it does and does not do

- **It changes no picks.** 0 of 3,722 changed historically, and 0 in 2025.
  - Scaling the width of the margin distribution never moves a probability
    across 50%, so it cannot change which side is picked.
  - It makes the cover probabilities slightly more accurate: a high-total
    game is closer to a coin flip, and a low-total game is more decisive.
  - **It adds no wins by itself.**
- **The effect is real but fading.**
  - The fitted slope of margin width on the total is positive in every
    training window.
  - It fell from about 0.05 (training through 2006–2008) to about 0.01
    (through 2018–2020).
- **As noted in advance, it does not fix the key-number shadow's lean
  toward the favorite.** That comes from where the distribution is centered,
  not from its width.

## Live changes

- **Totals are captured at lock.** Each lock run fetches the Parlay `totals`
  market in a separate request, so a totals failure can never break spreads.
  It takes the median of the Over point across books.
  - Verified 2026-09-25: 31 games, 13–14 books each
    (`docs/evidence/probe/20260925T174502Z/parlay_nfl_totals.json`).
- **Fallbacks:**
  - If there is no market total, the nflverse `total_line` is used, with the
    flag `TOTAL_FROM_SCHEDULE`.
  - If there is no total at all, the previous `shifted` estimator is used,
    with the flag `NO_TOTAL_SHIFTED_FALLBACK`.
- **The model version is now `total-shifted-empirical-argmax`.** Predictions
  also record `market_total` and `market_total_books`.
