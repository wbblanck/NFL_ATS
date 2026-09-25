# Phase 5 — Calibration: Pre-registration

Committed **before** any calibration result was computed.

## Inputs

The input is the walk-forward, out-of-sample P(home covers) from the Phase 4
default estimator (shifted empirical) for 2007–2021. The target is covering
the SBRO open, which stands in for the frozen line. c is the nflverse close,
which stands in for the market at lock. Pushes are excluded.

## Calibrators

Every calibrator is fitted **chronologically**. For test season s, it is fit
only on the out-of-sample predictions of seasons before s. Test seasons are
2010–2021, so each calibrator has at least 3 prior seasons.

- **raw:** no calibration.
- **platt:** logit(p′) = a + b·logit(p).
- **isotonic:** monotone step fit (pool-adjacent-violators) of the outcome on
  p, clipped to [0.01, 0.99].
- **platt_key:** logit(p′) = a + b·logit(p) + g·key.
  - This one targets the key-number bias disclosed in Phase 4.
  - The home team needs margin > t, where t = −(league line), and the market
    centre is m = −c.
  - key = #{K ∈ {±3, ±7} : t < K ≤ m} − #{K ∈ {±3, ±7} : m ≤ K < t}.
  - That counts the key margins lying between the threshold and the market
    centre, signed toward the side they favour.

## Metrics

- Measured on 2010–2021 pooled, and per season: log loss, Brier, expected
  calibration error (ECE), and a reliability table.
- **ECE buckets are defined after looking at the raw output range**, as the
  spec requires, but **before** looking at any calibrated output. Phase 4
  reported the raw 5th–95th percentiles as 0.39–0.58. So the buckets are:
  (<0.40), then every 0.02 from 0.40 to 0.60, then (≥0.60). That makes 12
  buckets. ECE is the count-weighted mean |mean p − hit rate| across buckets.

## Decisions fixed in advance

1. **Calibrator choice.** A calibrator replaces raw only if **both** hold:
   - its pooled log loss is lower than raw's, and
   - its pooled ECE is no worse than raw's.

   If several qualify, the one with the lowest log loss wins. Otherwise the
   engine stays raw.
2. **Pick rule.**
   - The live pick becomes "calibrated P > 0.5" only if that rule's pooled ATS
     win rate is at least the raw-argmax rule's on the same games.
   - Otherwise picks stay raw-argmax, and the calibrated probabilities are
     reported alongside.
3. **Gate.** The calibration report is produced (spec).
