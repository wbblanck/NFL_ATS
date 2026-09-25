# Game-Total Fix: Pre-registration

Committed **before** any result for the new estimators was computed.

## Hypothesis

A high-total game spreads its final margins wider than a low-total game with
the same spread. A wider spread changes the chance of covering a line that is
a few points away from the market. The live estimator uses one residual
distribution for every game.

## Data

- **Total:** nflverse `total_line`, the market total, available for every
  regular-season game 1999–2026. Like `spread_line`, it stands in for the
  market total at lock.
- Everything else is unchanged from Phase 4:
  - target = cover the SBRO open (2007–2021);
  - market = nflverse close;
  - training uses earlier seasons from 1999.

## Candidates (fit on training seasons only)

- **`shifted_total`**
  - Standardized residual z = (margin + c) / s(T), where
    s(T) = a + b·T.
  - a and b come from least squares of |margin + c| on T, scaled so that
    mean |z| matches the pooled mean of |margin + c| / σ.
  - F(t | c, T) = share of training games with z > (t + c)/s(T).
  - This keeps the shifted estimator's empirical shape and adds a
    total-dependent width.
- **`normal_total`**: margin ~ N(−c, s(T)) with the same s(T).

## Tests

- **Primary (decides):** walk-forward 2007–2021, with pooled log loss and ATS
  of "pick P > 0.5".
- **Confirmation (reported, cannot overturn):** 2025 with CBS opens, trained
  on 1999–2024.
- **Diagnostics:**
  - The fitted slope b, which must be positive for the hypothesis to hold.
  - Results by total tercile.

## Decision rule (fixed in advance)

- The best candidate replaces `shifted` **only if** its pooled log loss is
  lower than `shifted` **and** its ATS ≥ `shifted` on the same games.
- If adopted, live capture adds the market total at lock: the Parlay
  `totals` market, median across books.
- Otherwise nothing changes, and the result is reported plainly.

## Noted in advance

This targets margin *width*. It is not expected to fix `keynum`'s lean
toward the favorite, which comes from where the distribution is centered.
