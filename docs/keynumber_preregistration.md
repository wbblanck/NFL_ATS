# Key-Number Fix: Pre-registration

Committed **before** any result for the new estimator was computed.

## Problem (from Phase 4 and the 2025 holdout)

The live estimator ("shifted empirical") smears the real spikes of the final
margin at 3 and 7:
- **Model:** 3.5% of games at 3 and 2.7% at 7, for a home team favored by
  4–6.
- **Real games:** 8.7% at 3 and 5.9% at 7.

In the 2025 holdout, games whose CBS open was a whole number went 22-35.

## Candidate: `keynum` (key-number-weighted discrete normal)

- **Base:** margin k is an integer with
  base(k | c) = Φ((k + 0.5 + c)/σ) − Φ((k − 0.5 + c)/σ), centered on the
  market (−c). σ is fit on the training games.
- **Key weights:** w_|k| for |k| = 0…20. Each is
  (observed count of |margin| = |k|) / (sum over training games of the base
  probability of |k|). This is fit on training games only, and w = 1 for
  |k| > 20.
- **Final:** p(k | c) ∝ base(k | c) · w_|k|, renormalized per game.
  P(home covers S) = Σ_{k > −S} p(k | c).
- **No other tuning.** σ and w are refit each walk-forward season from past
  games only.

## Tests

1. **Primary:** walk-forward 2007–2021, exactly as Phase 4 (target = SBRO
   open, market = nflverse close, trained on earlier seasons from 1999).
   Metrics: pooled log loss, and ATS of "pick P > 0.5".
2. **Confirmation (reported, not used to decide):**
   - The 2025 holdout, exactly as `docs/holdout2025_preregistration.md` but
     with `keynum`.
   - 2023 and 2024 with the same method, **if** the CBS odds pages for those
     seasons still show opening lines. They are fetched after this commit.
3. **Diagnostics:**
   - The margin frequency at 3 and 7 against the real frequency.
   - Results on games whose frozen line is 2.5/3.5 or 6.5/7.5, where the fix
     should matter most.

## Decision rule (fixed in advance)

- **Adopt `keynum` as the live estimator only if**, on the primary test, its
  pooled log loss is lower than `shifted` **and** its ATS win rate is ≥
  `shifted`'s on the same games.
- Otherwise keep `shifted`, and report the result plainly either way.
- The confirmation seasons cannot overturn the decision. They are reported
  so a later reversal, if needed, rests on visible evidence.
