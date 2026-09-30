# Sharp-Book Market Estimate: Pre-registration

Committed before the results below were computed. Question: would the pick improve if the "market at lock" were a
sharp book's closing line (with its prices) instead of the consensus close? This decides whether new multi-book
captures are worth API credits.

Already seen (disclosed): docs/edge2_report.md used Pinnacle 2014–2017 opens, closes and prices, but always
against Pinnacle's own open and with a fitted price weight (H2, +4 net on 2014–2019). Not yet seen: Pinnacle's
close against an independent stale line, or a price adjustment that is not fitted.

## Data

- Seasons 2014–2017, the file's Pinnacle era (AusSportsBetting). Regular season.
- **Stale line (pool stand-in): the SBRO open**, independent of both closes. Pushes excluded; primary set =
  half-point SBRO opens (no push possible, as in the pool).
- Scores, totals and the baseline close: nflverse.

## Three versions of the live model (same margin distribution, fit on seasons before each season)

1. **Baseline:** market = nflverse consensus close (what the live model uses).
2. **Pinnacle line:** market = Pinnacle's closing spread.
3. **Pinnacle line + price:** market = the centre c at which the distribution gives Pinnacle's no-vig cover
   probability for its own closing spread (solved on a 0.05-point grid). No fitted weight.

## Decision

Primary comparison, on half-point SBRO opens: version 3 (and separately 2) against the baseline on games where the
picks differ, one-sided z, and log loss on all games. **Worth the credits** if version 2 or 3 beats the baseline with
z >= 1.645 and lower log loss. Otherwise the sharp-book refinement is not pursued. Reported: results on games where
the consensus close is within ½ point of the stale line (where the refinement is meant to help).
