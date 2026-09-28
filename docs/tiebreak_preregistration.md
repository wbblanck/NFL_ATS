# EPA/Efficiency as a Tie-Breaker in No-Move Games: Pre-registration

Committed **before** any result in this subgroup was computed. Only the subgroup's size (539 games) was checked,
to confirm the test is feasible.

## What the user asked for

- In games where the market has **not moved** off the frozen line, the line-movement model has no movement to go
  on. Its picks there are close to a coin flip (about 52% historically).
- The question: can EPA/efficiency differentials pick those games better?

## Disclosed in advance

- This is a **subgroup of the same 2010–2021 games** already used in phase 6 and in
  `docs/phase8_efficiency_report.md`, where adding the differentials to every game failed.
- A subgroup chosen after a failed overall test has a higher false-positive risk. The bar below is therefore set
  higher than phase 6's.
- **Expected result:** no improvement. Across all games, the differentials' correlation with the market's error
  was 0.00–0.03.

## Games

- **No-move game:** market at lock equals the frozen line (drift = 0).
- **Backtest:** nflverse close = SBRO open, over 2010–2021. That is 539 games, with pushes on the open excluded.
- **Live equivalent:** `market_at_lock == league_line`.
- **Reported as a diagnostic only:** ½-point-move games (702).

## Tie-breaker rule (no tuning on outcomes)

- **Differentials:** the four from the phase 8 test (`d_db`, `d_rush`, `d_sr`, `d_rz`), with the same point-in-time
  ratings and the same fixed hyperparameters (h = 6, s = 0.5).
- **Market-error model:** for test season s, an ordinary least-squares regression is fit on **all** games from
  2007 to s−1:
  - target: the market's error, margin − (−close);
  - predictors: the four differentials;
  - **no intercept**, so the rule cannot turn into "always pick home" or "always pick away".
- **Pick:** in a no-move test game, take home if the predicted market error is > 0 (home beats the market),
  otherwise away.
- **Comparator:** the live model's own pick in the same games (walk-forward `shifted_total`, as in phase 8).

## Decision rules (fixed in advance)

1. **Primary (decides), 2010–2021 no-move games.** The tie-breaker passes only if **both** hold:
   - it has more ATS wins than the live model on the same games;
   - a paired sign test on the games where the two pick differently gives **z ≥ 1.96**.
2. **2025 check (CBS open, half-point lines, market close = open).** Reported. The sample is too small to decide:
   likely under 60 games.
3. **Live change:** only if 1 passes. Even then it is proposed to the user first. It would be tracked live as a
   shadow pick for at least one full season before it could make the real pick.
4. **Diagnostics (reported, never decisive):**
   - the same rule on ½-point-move games;
   - the tie-breaker's ATS alone with its SE;
   - the fitted coefficients per season;
   - how often the two picks differ.
